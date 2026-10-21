# eRev Cloud 1.0: stated limits of the release

### October 20 — separately retained usage cancellation and re-entry segments

Realized-fee cancellation attribution now stops at the next disclosure re-entry. The final
cancelled version in that segment supplies realized fees at the same cut used for retained
revenue. Re-entry admits fixed plus realized allocation net of pre-entry revenue, and pre-entry
realized fees are excluded from in-scope VC changes. Previously, individual NEW_CONTRACTS and
VC_ESTIMATE_CHANGES lines could be wrong despite a zero unexplained total. New runs retain
rpo_cancelled_usage_v4; v1-v3 runs keep their prior scope and markers on rerun.

Seventy scoped reader cases pass, including one and repeated cancellation/re-entry with realized
fees, ranges beginning before or after cancellation, explicit expected line amounts and legacy
behavior. These adapt retained versions and are not a new public API reactivation journey.
Existing public modification reports/reruns in three currency views, scoped lint/types and
migration 0247 down/up IPE parity pass.

The new segment path requires distinct retained cancellation and re-entry versions. First-batch
or same-version usage cancellation followed by re-entry, multiple cancellations in one
computation, intervening pre-termination versions, same-day entry/cancellation and combined-member
aging ownership remain open. Independent accounting sign-off and final-candidate verification
remain open. No deployment and no claim of production readiness.


### October 20 — realized-fee attribution reaches a continuously cancelled version tail

First-batch, opening-version and later-version cancellation bridges can now use the final
retained realized-fee amount when every subsequent version remains included and cancelled,
contains the obligation and retains dated realization evidence. Final recognized revenue uses
the retained final version as before; this keeps later realized-fee corrections out of fixed
cancellation attribution. Original fixed modifications and estimates still require their
termination bridge. New bindings retain rpo_cancelled_usage_v3; v1/v2 runs preserve their earlier
scope and markers. Re-entry or missing evidence prevents the new tail reader from proceeding.

The 66 scoped cases now include positive/negative fee corrections through retained cancelled
versions for first entry, monthly opening and later termination, with legacy and missing-evidence
checks. These are adapted report-data witnesses, not a new public API cancellation journey.
Existing public modification reports/reruns in three views, scoped lint/types and migration 0246
down/up IPE parity pass. This supersedes the blanket multi-version usage limitation only for a
continuously cancelled and fully evidenced tail.

Usage chains containing re-entry, multiple cancellations within one computation, versions
intervening before termination, same-day entry/cancellation and combined-member aging ownership
remain open, along with independent accounting sign-off and final-candidate verification.
No deployment and no claim of production readiness.


### October 20 — single-computation cancellation can separate realized fees

A first-entry computation containing one later cancellation, or an opening-to-closing
cancellation within the same retained version, now uses dated realization evidence to separate
realized-fee changes. The VC line includes the realized change; cancellation removes fixed plus
realized allocation net of recognized revenue. Original fixed allocation changes still use the
retained modification/estimate bridge. Missing realization evidence does not authorize the new
path. New bindings retain rpo_cancelled_usage_v2; v1 runs retain their later-version-only rule
and preserve v1 again on rerun.

Eight new reader witnesses cover first entry versus monthly opening, positive/negative realized
changes, partial recognition and full revenue reversal, plus legacy classification. All 66 scoped
report cases pass, as do the existing public modification reports/reruns in three currency views,
scoped lint/types and migration 0245 down/up IPE parity. These reader cases do not establish a
new full-compute/public API usage-plus-cancellation journey.

Multi-version usage/cancellation chains, multiple cancellations within one computation, versions
intervening before termination, same-day entry/cancellation and combined-member aging ownership
remain open. Independent accounting sign-off and final-candidate verification remain open.
This supersedes the first-entry/same-version usage limitation only for the described single-
computation path. No deployment and no claim of production readiness.


### October 20 — realized fees in a later terminal version are separately attributed

With an opening obligation and one later terminating version, original dated realization on
both versions lets RPO use the terminating version's realized amount. Newly realized fees or
signed corrections are VC movements; their revenue remains on REVENUE and they do not distort
fixed cancellation attribution. Modification/estimate mixtures still require opening fixed
allocation plus original deltas to reconcile to the pre-termination boundary. Missing realized
traces do not authorize this path. New runs retain rpo_cancelled_usage_v1; older bindings retain
the previous classification on rerun.

Fifty-eight report-reader cases and six engine realization cases pass. Reader coverage includes
positive/negative/zero changes, prior revenue restatement and reversal, absent evidence and old
binding behavior. Existing public modification reports/reruns in three currency views and scoped
lint/types pass, with migration 0244 down/up IPE parity. This does not establish a new public
API usage-plus-termination journey or complete coverage of all usage/cancellation combinations.

First-entry and same-version usage cancellation, multi-version usage chains, multiple cancellations
within one computation, versions intervening before cancellation, same-day entry/cancellation,
and combined-member aging ownership remain open. Independent accounting sign-off and final-candidate
verification remain open. No deployment and no claim of production readiness.


### October 20 — retained versions no longer discard an earlier cancellation bridge

The original first-batch cancellation and an opening obligation's same-version cancellation
are now settled before the next retained version, provided that version is effective on or
after the original termination. Later cancelled versions supply retained revenue without
repeating the cancellation. Re-entry admits the remaining allocation after pre-entry revenue;
the earlier termination and revenue remain separately attributed. New bindings retain
rpo_cancelled_chains_v1, while earlier bindings preserve their previous classification.

Scoped checks use real engine cancellation traces with adapted retained-version and re-entry
chains, covering refund/non-refund endings, both estimate directions and full/monthly ranges.
These are not a new public API reactivation journey. Fifty scoped cases, the existing public
modification reports/reruns in three currency views, types/lint and migration 0243 down/up IPE
parity pass. This supersedes the prior blanket limitation on later retained versions only when
the original cancellation precedes the next version's effective date.

Versions intervening before cancellation, multiple cancellations within one computation,
same-day entry/cancellation and realized-usage mixtures remain outside this path. Combined-member
aging ownership, independent accounting sign-off and final-candidate checks remain open.
No deployment and no claim of production readiness.


### October 20 — original cancellation dates restore earlier RPO cuts

New computations retain per-obligation termination and pre-boundary end dates. Historical RPO
and close-variance reads use those dates to preserve a pre-cancellation remainder, including
its dated satisfaction status for partial exemptions. A fixed-only first retained computation
with entry and one later cancellation can separate original modifications/estimates, revenue
and the cancelled remainder. Same-version monthly cancellation uses the reconciled original
pre-termination bridge. Missing dates in older traces preserve legacy behavior; no dates are
backfilled. New metadata cannot appear in previously retained computations.

Full engine witnesses cover both estimate directions, ordered same-day estimates/termination,
refund and non-refund endings, standalone historical RPO, historical variance and full/monthly
rollforwards. Fifty scoped cases and existing public modification reports/reruns in three views
pass, with lint/types and migration 0242 down/up catalogue parity. The currency journey is an
existing modification workflow, not a new public API first-entry cancellation witness.

Multiple cancellations, first-entry cancellation followed by another retained version in the
same range, same-day entry/cancellation, realized-usage mixtures and historical intermediate
term changes remain outside this new path. Combined-member aging date ownership still needs a
policy decision. Independent accounting sign-off and final-candidate verification remain open.
This supersedes the blanket first-entry cancellation limitation only for the supported case.
No deployment and no claim of production readiness.


### October 20 — same-day estimates can precede a cancellation

The cancellation bridge now uses immutable contract-event record sequence to distinguish an
estimate before termination from one after it on the same date. The order matches the engine's
(effective date, record sequence, event key). The original pre-termination amount must still
reconcile; missing sequence or a later estimate cannot be inferred to precede cancellation.
New runs retain rpo_cancelled_changes_v2. Existing v1 runs retain their former date-only
classification and preserve the v1 marker through reruns.

Full-compute cases cover both estimate directions, same-day termination, absent/reversed order
and legacy behavior. Public modification reports/reruns, types/lint and migration 0241 catalogue
parity also pass. This supersedes the blanket same-day estimate limitation where original order
is available. First-entry cancellation batches, multiple cancellations and usage mixtures remain
open, as do combined-member aging ownership, independent accounting sign-off and final-candidate
verification. No deployment.


### October 20 — mixed terminal cancellation attribution requires an original bridge

For an already disclosed obligation, a later retained version containing modification/estimate
changes and a single terminal cancellation can now separate those changes. Opening fixed
allocation plus original deltas must equal the retained pre-termination allocation, with complete
modification evidence and unambiguous event order. Cancellation removes the remaining allocation;
recognized revenue and prior-period revenue restatements stay separately identified. New bindings
carry rpo_cancelled_changes_v1; older runs retain their previous classification. Posting amounts
are unchanged.

Full-compute traces exercise a concession, upward/downward estimate change and nonrefundable full
termination; scoped rollforward cases cover recognized/reversed/restated revenue and realized
consideration, and reject a mismatched bridge. The existing public modification/report rerun
journey remains valid in three currency views. This is not a full public mixed-cancellation
workflow acceptance claim. First-entry-and-cancel batches, multiple cancellation events, usage
mixtures and estimate changes on the termination day remain unexplained when their ordering or
source bridge cannot be proved. Combined-member aging ownership, independent accounting sign-off
and final-candidate verification remain outstanding. Migration 0240 records the rule; no deployment.


### October 20 — creation evidence closes the first-batch added-obligation gap

New engine traces explicitly retain whether an obligation existed before its modification boundary
and the original event sequence. First-batch RPO may treat an earlier missing subject boundary as
pre-creation only when creation is explicit and another obligation retains the earlier event's
order. This handles same-day modification followed by addition without manufacturing zero rows.
Zero amounts alone never establish absence. Missing creation/order or post-creation boundaries
remain unsupported, and older traces are not backfilled.

Full-compute cases cover a concession, same-day addition and later positive/negative estimate
movements, original trace replay and historical/monthly RPO cuts. Public modification reports in
three currency views and reruns remain valid. Migration 0239 documents this evidence. This
supersedes the prior blanket limitation for first-batch obligations lacking pre-creation rows;
legacy evidence gaps and cancellation mixtures remain. Combined-member aging date ownership,
independent accounting sign-off and final-candidate checks remain outstanding. No deployment.


### October 20 — monthly translated exemption movements are reviewable

Converted RPO rollforwards retain contract-period exemption movements in transaction currency and
the exact translated amounts used in EXEMPTIONS. These details explain nonzero translated flows
when opposite original movements cancel across the requested range. The viewer, Excel and PDF
present the monthly bridge; CSV manifests retain the records. Existing obligation-level endpoint
exclusions remain in their original currency and are not represented as translated amounts.

New bindings carry rpo_exemption_translation_v1; older bindings keep their control shape. The
witness covers EUR/USD and EUR/USD/GBP translation with opposite 100 original movements, net
translated movements of 20 USD / 16 GBP, separate FX and zero rounding. This feature explains
existing arithmetic rather than changing it. Combined-member aging date ownership, missing
first-batch modification evidence, independent accounting sign-off and final-candidate checks
remain open. Migration 0238 documents the new evidence. No deployment.


### October 20 — added obligations no longer inflate new-contract RPO

New report runs distinguish a new obligation on an already disclosed contract from a contract
entering disclosure. The former follows its amendment/estimate causes; first entry and
cancellation re-entry retain their existing rules. Missing original evidence for mixed causes
still leaves the change unexplained. Bindings carry rpo_added_obligations_v1 so older runs keep
their original classification; converted monthly projections use the same selected behavior.

A real approved Marrowby addition and redistribution now reports the full 60,000 as MODIFICATIONS,
zero NEW_CONTRACTS and zero UNEXPLAINED. All ties and identical reruns pass in transaction,
functional and reporting views (USD for this witness). Scoped cases also cover mixed estimates,
legacy output, exemptions and re-entry; migration 0237 matches the catalogue after down/up.
This does not repair missing first-batch boundary evidence or decide combined-member aging date
ownership. Independent accounting sign-off and final-candidate verification remain outstanding.


### October 20 — first-batch RPO modification and estimate attribution

New computations retain original fixed-allocation amounts before and after each modification
boundary, including zero changes for unaffected obligations. First-entry RPO batches can separate
later modifications and estimate changes from new contracts when the obligation has complete
boundary evidence. For movements within one retained version, the original modification deltas
and estimate shares must jointly reconcile to the dated fixed-allocation difference. Earlier
reporting periods exclude future movements. Invalid boundary arithmetic is rejected.

This does not reconstruct missing historical evidence or infer amounts for an obligation without
a complete boundary history (for example, some obligations added after an earlier modification).
Cancellation mixtures retain the existing admission/removal rules and limitations. Previously
retained traces remain unchanged. Native price-only modification with both increasing and
decreasing estimates, original trace replay, historical/monthly cuts, the existing K01 public
rollforward and migration 0236 catalogue parity were checked. Combined-member aging date ownership,
independent accounting sign-off and final-candidate verification remain outstanding.


### October 20 — historical GL selection cannot fall back to stale reviewed evidence

New GL comparison bindings (v4) choose the latest reconciliation identity eligible at the report
cutoff before inspecting its mutable state. Previously, a later update excluded that row from
the query and could select an older reviewed reconciliation, falsely passing a historical report.
If the selected source changed after the cutoff, its historical review state and totals are not
assumed: the comparison is NOT_APPLICABLE and retains the source identity and explicit reason.
Current post-cutoff amounts and status are not copied into that historical report.

Existing v1/v2/v3 bindings keep their original retained controls. Previously accepted v4 runs
and newly unavailable v4 runs also replay from their own retained evidence. The public API case
uses two reviewed sources, reopens the latest after the cutoff, and verifies both balance reports
and their reruns. The existing review workflow, 12 scoped controls, lint/types, and migration
0235 down/up IPE parity pass. This does not reconstruct mutable source history that was never
retained. Combined member-aging date ownership, accounting acceptance and final-candidate release
checks remain outstanding. No deployment.

### October 20 — actionable GL comparison review; member-aging decision pending

The viewer displays GL comparison evidence in a table with separate GL, retained subledger,
report closing and three difference columns. Comparison and bridge outcomes, retained review
status and reconciliation links remain visible per row. Users can filter recorded discrepancies
or unavailable comparisons without recalculating the report. Missing numbers are not zero;
older details without recorded row results are not promoted to PASS. General notes, including
the functional-currency comparison basis, stay visible under filters. Targeted viewer checks,
TypeScript and scoped lint pass. This adds no accounting logic or deployment.

For combined-contract liability aging, S10-R-23 and S12 retain member liability totals, while
original liability layers carry payment-owner dates. The current sources do not determine a
unique member-to-original-date assignment. The owner has been asked to choose between preserving
payer-owned aging with a separate member-allocation adjustment and allocating original dated
layers on the existing member liability basis. This choice is pending; no inferred date-allocation
policy has been implemented. Independent accounting acceptance remains outstanding.

### October 20 — locked balance aging and historical manifest compatibility

New locks now include BALANCE_AGING in all three currency views. The original period-end
buckets, amounts and reporting translation controls are frozen together; locked reads, CSV
exports and close evidence archives cannot re-age balances or re-read rates. Re-lock comparison
tracks bucket movements separately from changes to totals. The report viewer exposes currency
selection while keeping the frozen scope fixed. Migration 0234 extends the snapshot kind and
records its source in the report catalogue.

Old twelve-kind manifests remain verifiable and exportable with their original hashes. They
have no aging dataset: an aging request against such a lock refuses explicitly. Nothing is
backfilled from current business data. Current freeze writes still require every current kind.

The original-source limits of functional aging still apply. In particular, combined-member
owner layers that do not reproduce dated member functional balances are unsupported; the
builder refuses instead of assigning ages by an invented ratio. Because new closes now freeze
aging, incomplete original aging evidence can block their dataset freeze. Old computations may
need recomputation to supply retained aging traces. This change does not claim to resolve those
underlying ownership gaps or independent accounting acceptance.

Targeted validation covers three-view API reads/CSV exports without live builder calls, a real
foreign-currency close-run freeze, a public approved lock, old/new evidence archive verification,
aging bucket re-lock differences, viewer selector restrictions, lint/types and migrated IPE parity.
No deployment was performed. Final-candidate checks and independent accounting sign-off remain.

### October 20 — priced RTI advance-billing source defect resolved

The shared right-to-invoice selector now uses delivered quantity times the booked unit price
when that price exists, including zero performance before any delivery. Previously an advance
invoice was treated as the fallback performance source until the first delivery; the switch
could change the measured consideration and break the S04-R-02 allocation identity. Rated
usage retains priority, and invoice fallback for unpriced lines remains unchanged. This does
not introduce a new over-billing admission rule or rewrite stored computations.

Whole-engine regression checks assert price, allocation and revenue before performance, after
performance and after additional invoices. The recorded EUR case now recomputes successfully:
20,000 billed versus 10,000 performance revenue leaves 10,000 transaction liability, whose
historical USD carrying is 11,050 (5,500 from August plus 5,550 from September). Public functional
aging preserves both original dates and reconciles. Related RTI checks, lint and types pass.
This resolves that specific diagnostic; independent accounting acceptance, broader lifecycle
verification and final release-candidate checks remain open. No deployment.


### October 20 — original functional aging attribution

Foreign asset/unbilled aging now reads original functional S12 reclass shares with S10 revenue
dates. Liability aging reads original functional layer creations, consumptions and signed
remeasurements, without resetting creation dates. Both historical layering and the approved
monetary override are supported. Every member/role must reconcile to its retained dated
functional balance; the report refuses missing/corrupt attribution and unmatched member
ownership. It does not infer a combined member's age distribution from a grand-total ratio.
New bindings retain this path; earlier bindings preserve their original behavior. Reporting
translation continues from functional balances with retained closing rates and conserved totals.

Four API journeys cover EUR unbilled remeasurement at two dates and bound reruns, USD/GBP
historical and monetary liability layers before/after partial consumption, and existing
reporting translation. Pure checks validate original dates, split roles and invalid sources.
Migration 0233 roundtrips and matches the IPE catalogue. Combined-member functional age
allocation beyond reconciling original owner layers, locked aging datasets, broader lifecycle
acceptance, independent accounting acceptance and final candidate checks remain open.

Earlier engine finding, resolved by the priced RTI source fix above: starting with `close_run_worlds.eur_receivable` (EUR 100/hour,
100 hours delivered August 31, no invoices), append EUR 15,000 billing dated August 1 and EUR
5,000 dated September 1, then recompute. The engine raises S04-R-02 (`sum a_posted =
allocation_basis`). That scenario is now covered by its own engine and report regression; fixed-price liability
journeys alone did not establish its correctness. No production-readiness claim and no deployment.


### October 20 — reporting-currency aging view

For supported functional aging balances (transaction and functional currency coincide),
reporting view now translates age buckets using approved retained closing rates. Previously
that request returned untranslated amounts. Source currency/rate columns and retained rate
facts make the translation visible. Cumulative bucket rounding preserves the translated
contract/role total; the balance tie-out stays explicitly in functional currency. Earlier
bindings retain their original outputs.

The GBP-to-USD public report and bound rerun pass, alongside existing asset/unbilled aging and
later-billing rerun regressions. Core checks include signed sub-cent rounding without a total
drift. Migration 0232 roundtrips and matches catalogue IPE. This does not implement foreign
transaction-to-functional age-layer attribution or locked aging datasets. Those boundaries,
independent accounting acceptance and final candidate verification remain open. No deployment.


### October 20 — waterfall contract entry cutoff

The B4-1/C-3 population gap is implemented for new calculations: each performing entity's
as-of period end excludes contracts whose first included-chain entry is later. The existing
historical entry rule uses the first included version's book-specific activation, criteria-met
or opening event, with that version's effective date as fallback. Later measurements batched
with activation cannot postpone entry. Dated entry evidence and original version identities
are retained; legacy bindings and previously frozen datasets preserve their original content.

API journeys cover exclusion before entry, inclusion afterward, deterministic reruns,
performing-entity journal agreement, restricted access, forecast FX and both regrouping
computation orders. A pure binding check covers entity-specific calendar endpoints, legacy
semantics and absent evidence. Migration 0231 records the rule and event source. This is not
independent accounting approval or full release acceptance; those remain outstanding.


### October 20 — structured GL reconciliation exports

Excel now exposes retained GL bridge evidence as filterable numeric workpaper rows rather
than a concatenated text cell. Separate currency, role, source identity, review state, GL,
subledger, report and difference columns preserve the original result. Missing evidence is
blank and unavailable reasons remain visible; exporting never performs new accounting math.
This applies to standalone reports and disclosure workbook sections. Focused renderer checks
cover offsetting failed differences, reopened sources, missing subledger evidence, numeric
precision and formula-safe text. Independent accounting acceptance and final release checks
remain outstanding. No deployment.


### October 20 — reviewed GL source requirement

New balance and rollforward reports require the latest retained GL reconciliation to be
reviewed or certified before comparing its amounts. Draft, prepared, reopened and missing
statuses are unavailable, even when all amounts agree. Source links and review status remain
visible. Versioned v3 bindings preserve that review decision on rerun; legacy v1/v2 bindings
retain their original arithmetic-only semantics without reading current review state.

Focused public API journeys cover draft/review/reopen, retained reruns and foreign functional
balances. Migration 0230 records this requirement in both IPE definitions. This adds a source
review gate, not independent accounting acceptance or a production-readiness claim. Broader
lifecycle/close acceptance and final release-candidate checks remain open. No deployment.


### October 20 — deterministic Step-1 netted forecasts

Historical time-based forecasts now freeze original 25-7 deposit releases and cite each
obligation's attributed deposit share when netting manual-adjusted targets. A separate dated
reporting remainder removes already-recognized deposits from forecast reconciliation without
changing the contract's stored revenue/scheduled/awaiting measurement identity. Later manual
adjustments cannot rewrite the earlier projection; a fully recognized deposit leaves zero
future forecast. Old traces receive no inferred deduction.

Six engine journeys cover all three manual schedule kinds and partial/full prior recognition,
with trace replay and original period comparisons. Contract/report readers preserve the two
bases and reject negative or excessive reporting remainders. Migration 0229 describes the
source chain. Arbitrary source-changing/event-driven forecasts, broader public API lifecycle
and close-pass acceptance, independent accounting sign-off and final release checks remain
outside this verification. No deployment.


### October 20 — royalty manual projection from original sources

Fixed-guarantee plus royalty manual releases, deferrals and overrides now retain original-cut
statement/accrual sources. Both event and estimate-pin effective/application dates are frozen;
future statements, accruals and releases cannot change that forecast. Minimum guarantees,
recognized amounts and source populations must remain stable over the projected horizon.
Separate projection nodes avoid duplicating the live true-up evidence.

Override respread now includes recognized royalties at its anchor and preserves subsequent
signed royalty changes separately. Six JPY journeys cover positive and below-guarantee statement
corrections, all three adjustment kinds and a later accrual/release. The approved manual-release
floor still applies after a downward correction. Trace replay, original future schedules and
dated remainder reconciliation are checked through the contract trace reader.

This supersedes the generic royalty-mixture refusal for these supported snapshots. Netted
mixtures, broader API lifecycle and close-pass acceptance, independent accounting sign-off and
final release checks remain outstanding. Migration 0228 describes the path. No deployment.


### October 20 — fixed plus realized usage manual projections

Manual releases, deferrals and overrides now project fixed plus PERIOD_VC targets from the
original reporting cut. Realized usage is frozen and separately retained as trace inputs;
subsequent events do not become historical forecast amounts. Every projected period must
reconcile with the original schedule and dated remainder. Snapshots whose realized amounts
change over the future horizon still refuse rather than inventing fixed component allocation.

The override engine also now retains already-realized consideration in its respread anchor,
while later realized usage is recognized immediately through an explicit formula parameter.
Without that correction a 1,200 fixed fee plus 100 realized usage finished at only 1,200 after
a schedule override. Legacy formula traces retain their original behavior with a zero default.

Royalty/netted mixtures and broad public API lifecycle/close-pass acceptance are not established
by this change. Independent accounting acceptance and release verification remain outstanding.
Migration 0227 describes the report capability. No deployment.


### October 20 — combined-member agent refunds now source-attributed

A two-contract USD/GBP journey exposed GBP 75,600 of unexplained rollforward OTHER after
crediting and returning the agent contract in full. The report now discovers full-return
recipients from negative posted controls when current targets no longer retain prior reliefs,
and classifies billing from original asset evidence even when that amount is zero. Group
endpoint/source bridges remain independently validated; no residual is used to force balance.
New binding capabilities preserve historical reruns. Migration 0226 documents the behavior.

This covers two source-owner deposits, both deliveries, the full credit/return and retained
public report reruns in transaction, functional and reporting currency. It does not establish
broad close-pass acceptance, arbitrary mixed manual-adjustment projection, independent
accounting sign-off or full production readiness. The existing gross-relief disclosure policy
is unchanged. No deployment.


### October 20 — agent credit memo and full-return defects resolved

The representative gross-control reversal case is now implemented and verified. Returned units
advance the agent transfer boundary so earlier credit memos participate in gross billing. Zero
split weights retain explicit zero role targets instead of leaving old cumulative amounts in
place. Before this fix the return was quarantined because the entry did not balance; omitting
the transfer-boundary fix also left gross billing and supplier balances outstanding.

The two-prepayment journey fully reverses 90,000 gross, 18,000 net revenue and 72,000 supplier in
USD, with every role also netting to zero in GBP. Source attribution validates both currencies;
the September public reports and retained reruns pass all views. The reversal settles the
credit-memo asset and is not relabelled as opening-liability relief. Single-layer and zero-net
cases remain passing. Explicit empty split baselines require an original zero input, calendar
and absence of earlier functional sources; missing later history is not treated as zero.

Cross-contract agent groups and broader close-pass acceptance still need coverage. Existing
agent disclosure presentation and independent accounting acceptance remain open, as do final
release-candidate checks. No deployment or overall production-ready claim.


### October 20 — multi-layer agent gross relief now attributable

Two original prepayment layers no longer require guessing how the net/supplier split belongs
to each layer. The gross control line provides original source ownership through its target,
prior target and paid history; each net/supplier component independently reproduces its scalar
split formula and paid history in transaction and functional currency. Scalar verification
contains no attributed movements and is rejected by the attributed posting-delta reader.
The fallback catches only ambiguous split ownership, not arbitrary invalid evidence.

A two-deposit DB journey confirms both original layers and subsequent supplier paid history,
then exercises both public report consumers in all currency views with retained reruns. The
single-layer and zero-net cases pass as well. Close envelopes must explicitly retain revenue
control history; legacy envelopes without it remain unavailable. Cross-contract agent groups,
gross-control reversal histories and broader close-pass acceptance remain to be exercised.
Individual net/supplier per-owner allocation is still unavailable without original evidence.
The existing gross-relief disclosure column policy is unchanged and still needs independent
accounting acceptance. No deployment or overall production-readiness claim.


### October 20 — production revenue posting-class scope correction

The previously listed “dedicated public mixed-period TIME workflow” is not a missing workflow
under current production policy. S13 costs_view deliberately leaves revenue released_at_close
empty (L3-2-Q-15): both scheduled NORMAL revenue and TP_CHANGE post as EVENT. A schedule row's
is_released_at_close flag does not override this posting policy. The recently added mixed-TIME
reader remains conditional support for original producers that explicitly supply TIME amounts;
it is not evidence that the public product emits such revenue targets, nor a reason to change
posting timing. Earlier broad claims about this being an outstanding live reporting feature
are superseded by this finding.

The actual public scenario is a prepaid service with a reviewed variable-consideration bonus.
For May it has NORMAL 3,224.18 and TP_CHANGE 445.05, totaling 3,669.23 GBP; original revenue
counterparts remain EVENT-only. Both public reports pass transaction, functional and reporting
views and retained reruns, with zero unexplained OTHER and passing balance ties.
Multi-origin agent split attribution and other documented dated
projection limits still need engineering work. Independent accounting sign-off remains absent;
no deployment or overall production-ready claim is made.


### October 20 — mixed-period TIME amounts retained and consumed

S14 now records the differences of its actual cumulative TIME targets per period, independently
in transaction and functional currency. Reporting uses these retained amounts when a mixed
period has exactly one original provenance, even if the cumulative input spans multiple other
periods and owners. Original owner, layer, kind, date and source identity are preserved. Global
TIME totals must reconcile in both currencies. No amounts are allocated across ambiguous owners.

An original S14 mixed-period output is exercised through the reader; scoped source cases cover
signed currency amounts and missing/changed evidence. The existing DB intercompany public-report
and rerun workflow passes. A dedicated public mixed-period workflow is still unverified, and
multiple owners inside the same mixed period, multi-origin split inputs and independent
accounting acceptance remain open. Old envelopes without the finer retained amounts remain
unavailable for this new path. No deployment or overall production-ready claim.


### October 20 — zero-net agent counterpart now supported

The missing-counterpart failure for zero-net agent entries is resolved: exactly one supplier
line may balance the control line without a synthetic revenue line. Its original gross input,
signed source movements, amounts and currencies must reconcile. The retained evidence labels
the supplier counterpart. This also handles the engine's unsplit all-to-supplier target.

The public two-report DB journey now covers both zero and nonzero fees in transaction,
functional and reporting views with retained reruns. It confirms no unexplained rollforward
OTHER and passing balance tie-outs. Broader close-pass/reversal acceptance is not claimed.
Multi-origin split inputs, within-period mixed-source attribution and independent accounting
acceptance remain open. The existing gross control-relief disclosure policy is unchanged.
No deployment or overall production-readiness claim.


### October 20 — agent supplier history and gross/net source attribution

The supplier-history and gross/net matcher gaps in the preceding entry are now implemented.
The reader includes only revenue-recognition BILLING_CLEARING/AP_SUPPLIER lines and verifies
original clearing purpose, amounts and paid history. Agent gross control relief must reconcile
to separately verified net revenue and supplier legs in transaction and functional currency.
Both components remain explicit in retained report evidence. The existing opening-liability
report's revenue_recognized column follows the gross control-relief family: this fixture shows
90,000 there, while the separate net revenue component is 18,000. This patch does not change
that disclosure policy; its agent presentation still requires independent accounting acceptance.
Original split formulas and
minor-unit rounding require a uniquely owned source; they do not infer ownership by weights.

The two-delivery DB workflow exercises both public report consumers in transaction, functional
and reporting views, including retained reruns; the actual merchant engine example separately
reproduces 120,000 gross / 19,200 net / 100,800 supplier. Old close-pass envelopes lacking the
supplier-history capability remain unavailable. This does not establish multi-origin split,
zero-net agent or broad close-pass agent acceptance; within-period mixed-source cases and
independent accounting sign-off remain outstanding. No deployment or production-ready claim.


### October 20 — split-role formula reader; agent integration still open

The internal revenue reader can replay a split role target for a single uniquely owned revenue
input, checking original weights/index/sign and minor-unit rounding in both currencies, plus
retained TIME/EVENT amounts. Scoped formula/source checks pass. This does not make the complete
agent report path available: its control-to-revenue entry matcher still requires equal gross
relief and net revenue, and retained revenue history does not yet include the AP_SUPPLIER leg.
Supplier history and explicit gross/net component reconciliation remain required before public
agent workflow acceptance. Multi-origin split inputs and independent sign-off remain open.
No deployment.


### October 20 — readable exemption export details

XLSX and PDF now present retained RPO exemption facts as readable records with original
transaction-currency amounts and named rules. XLSX numeric cells preserve signed amounts;
wrapped text keeps long rule names readable. PDF uses existing wrapping and pagination.
The CSV companion manifest retains the original detail array; the CSV grid stays unchanged.
A 120-record check exceeds Excel's single-cell limit and confirms that records are not lost.
This is export presentation, not a change to accounting amounts or the remaining mixed-source
limitations. Independent accounting sign-off is still outstanding. No deployment.


### October 20 — RPO exemption endpoint details

The RPO rollforward report and run pages now display obligation-level exemption details:
contract/entity, opening and closing dates, applicable rules, excluded amounts and the signed
movement. This includes full eligibility changes and partial POL-200 release. These are the
original transaction-currency endpoint figures; functional/reporting views say so explicitly
and do not present them as translated movement amounts. Existing report totals are unchanged.
New retained bindings enable the details while legacy rebuilds preserve their earlier shape.

Scoped policy/endpoint and viewer checks pass. Broader mixed-source functionality, public
workflow acceptance and independent accounting sign-off remain open. No deployment.


### October 20 — mixed sources across recognition periods

Mixed cumulative revenue inputs can now retain separate original owners/layers across periods
whose S14 relief causes are uniformly TIME or EVENT. The reader matches the exact original
subject/period source keys and reconciles both currency TIME totals, with no allocation ratio.
Same-period mixtures, missing classifications and functional TIME amounts that do not equal
classified original sources remain unavailable. Split-role and non-revenue component inputs
remain open. Existing single-provenance and legacy paths are preserved.

Scoped engine/source checks and intercompany DB compatibility pass; these do not establish
full public mixed-workflow accounting acceptance. Independent accounting sign-off and final
release verification remain outstanding. No deployment.


### October 20 — foreign-currency freeze compatibility restored

The DATASET_FREEZE failure recorded under the three-way GL bridge is resolved. FX source
attribution now recognizes the additional S14 TIME/EVENT annotations as descriptive metadata,
while continuing to derive source ownership and amounts from retained S12 layers and reconcile
current targets, prior targets and paid history. Genuine split-role parameters remain refused.
Seven scoped source cases and the previously failing two-month foreign-receivable DB journey
pass, along with locked-endpoint reruns in both functional and reporting views. This restores
that workflow; it does not complete every mixed-source or multi-currency
scenario, and independent accounting sign-off remains outstanding. No deployment.


### October 20 — retained three-way GL bridge

New balance and rollforward runs compare the report closing caption, the reconciliation's
retained subledger caption and its GL caption per entity and role in functional currency.
Both bridge legs are visible; any nonzero leg fails even when the report-to-GL net is zero.
Missing retained subledger amounts remain unavailable. Retained v1 runs preserve their original
two-way comparison; v2 binds the new evidence without reading current GL data on rebuild.

The uploaded-trial-balance DB journey and scoped backend/viewer cases pass. The existing foreign
contract balance journey fails at close DATASET_FREEZE before report comparison; rerunning with
the original GL implementation reproduces that failure. It remains unresolved and must not be
counted as multicurrency acceptance. Broader mixed-source/lifecycle support and independent
accounting sign-off are still outstanding. No deployment.


### October 20 — internally mixed revenue with unique provenance

Revenue attribution now accepts an internally mixed TIME/EVENT input when its original sources
identify one contract, layer, movement kind, date and source key, and the role target retains
exact signed per-input TIME amounts in both currencies. The report preserves the original S14
functional allocation and reconciles the TIME totals; it introduces no ownership ratio.

This does not solve inputs spanning multiple original provenances, split-role inputs,
non-revenue component inputs or mixed legacy targets without the new amounts. Scoped engine
and source tests plus the existing DB intercompany progress-reversal journey passed; they do
not establish acceptance of every public mixed-source workflow. Independent accounting sign-off
and the wider remaining reporting work are still open. No deployment.


### October 20 — manual adjustments in historical schedules

Fixed-only time-based schedule projections now replay manual releases, deferrals and schedule
overrides effective at the original reporting cut. Later events, allocation segments and
contract-status transitions are excluded from the snapshot. Six real engine cases cover each
adjustment kind followed by a release or estimate change and compare every future period with
the original pre-change schedule; the resulting trace chains reproduce their values.

This does not establish arbitrary mixed fixed/realized or netted manual adjustment projection,
or full public API acceptance of combined lifecycle scenarios. Unsupported component mixtures,
invalid original-cut projections and snapshot/revenue mismatches retain explicit errors instead
of silently falling back to current schedules. Original calendar/term gaps, legacy evidence and
independent accounting acceptance remain open. No deployment.


### October 20 — dated recognition-hold classification

Scheduled versus awaiting-trigger remainder now follows retained per-period engine evidence,
reconciled to the original version state. A later recognition hold or release cannot substitute
its state for an earlier reporting cut. Earlier time-based schedule projections also exclude
later hold/release effects. Real engine cases cover an open hold and hold-then-release through
three period cuts, including trace replay and the contract/report reader.

Arbitrary manual adjustment projection and combined hold/modification lifecycle acceptance
remain open, along with missing original calendars/terms and legacy traces without dated
remainder evidence. This update does not establish full production readiness or independent
accounting acceptance. No deployment.


### October 20 — historical deterministic schedule evidence

Historical RPO and waterfall schedules now freeze the original time-based allocation segment
at a reporting cut before a later fixed change. Original terms, progress, exact targets and
posted differences are retained and replayable. Report reads reconcile the dated projection
to the scheduled remainder; drill-through names the cut. Positive and negative estimate cases
match the original future schedule by period. This closes the latest-allocation backfill gap
for this supported path, not every historical modification or lifecycle case.

Update: independent period trace projections now preserve historical future amounts even when
later changes remove the current schedule lines. RPO and waterfall use these projections with
cut/period-specific obligation-version drill-through. A real engine decrease-to-zero case also
exercises both report readers without surviving schedule rows; this is not a full public API
lifecycle acceptance test for every kind of contract modification.

Remaining: missing original calendar coverage or segment terms, held/manually adjusted cuts,
and legacy traces without dated evidence need further work. No proportional schedule or
unexplained plug is used. Broader compound attribution and independent accounting acceptance
remain open. No deployment has been performed.


## Reporting GL source navigation and inventory — October 20, 2026

- New GL tie-out details retain the source book and period key and link to that exact
  reconciliation in the viewer. Earlier retained evidence without the route metadata still
  renders its amounts without guessing a destination. Re-runs use retained source evidence.
- Corrected obsolete B4-3/4/6/8/12 and C-11 inventory claims: 59 of 59 definitions have
  execution paths (55 builders plus four composed reports). Registration is not accounting
  acceptance; the detailed scenario limitations and independent accounting review remain open.
- Necessary verification: two focused GL backend tests and the offsetting-role viewer test
  passed; backend lint/type checking and frontend TypeScript checking passed. No deployment.

## Contracting intercompany revenue counterparts and reversals — October 20, 2026

- Revenue control attribution now resolves the contracting entity's INTERCOMPANY_DUE_TO leg
  within the same posting/entry/entity/contract. Original target, selected line, both currency
  amounts and recursively retained paid history must agree. It does not substitute the other
  entity's REVENUE leg or currency. Report evidence explicitly identifies the counterpart role.
- Ordinary computation history captures due-to lines at the original sealed cutoff. New close
  evidence declares the retained revenue roles; old close documents without due-to coverage
  refuse intercompany attribution rather than treating missing history as zero.
- Transaction reversal disclosure now uses the same original counterpart sources and separates
  asset/new-liability effects from consumed opening liabilities. Earlier legacy bindings retain
  their original builder. Functional/reporting intercompany relief uses the retained source proof.
- Presentation bridge v6 includes source-backed same-currency groups as well as foreign groups,
  including a return-month-only range whose original consumption predates the range. Earlier
  v1-v5 bindings retain their scope. Migration 0206 describes the expanded report logic.
- Real approved cross-company progress scenario: one member advances GBP 8,000; another member
  performs through AVM-US and recognizes GBP 4,000 in May, then revises progress to recognize
  GBP 2,000 cumulatively in June. Full-range opening relief remains GBP 4,000; June alone has
  GBP -2,000 revenue and zero opening relief because the reversal creates a new liability.
- Necessary checks passed: approved intercompany progress reversal in transaction/functional/
  reporting views, full-range and reversal-month-only identical reruns, ordinary cross-member
  return regression, real FX close evidence, catalogue migration, scoped lint and types.
- Mixed TIME/EVENT source allocation remains unimplemented in the generic close-release part
  interface. Current public ordinary revenue binding leaves released_at_close empty and posts
  relief as EVENT; do not infer TIME ownership from period-end source dates. Performing-side
  cross-calendar cases, close-only revenue histories, complex group changes and other documented
  release gaps still require work. No deployment or production-readiness claim.

## Cross-member billing asset settlement and excess liabilities — October 20, 2026

- Functional/reporting billings now retain signed asset-settlement amounts and both sides of
  cross-member asset transfers from the original billing layers. Layer currencies, transaction
  totals, functional amounts and trace identities must already reconcile before presentation.
- Asset bridge v2 distinguishes billing that settles an asset from excess billing that creates
  a liability, including when the invoice issuer has no asset of its own. Both billing roles
  and corresponding member adjustments follow original source amounts, never unexplained OTHER.
  Monthly and whole-range amounts are bound; earlier asset-bridge v1 bindings retain their path.
- Billing and revenue-return asset transfers are combined without replacing either population.
  The billing source method is recorded even for empty populations, preserving rerun scope.
  Migration 0205 documents the expanded report logic.
- The real foreign combined scenario invoices USD 60,000 after another member recognizes
  USD 54,000: at retained spot .84 it settles GBP 45,360 of the other member's asset and creates
  GBP 5,040 of liability for the issuer. Asset balances close to zero; issuer billing remains
  split across the two roles and no member has unexplained OTHER.
- Necessary checks passed: asset and liability report views in functional/reporting currency
  with identical reruns, cross-member revenue-return regression, catalogue migration consistency,
  scoped lint and types.
- Mixed TIME/EVENT source allocation, intercompany counterparts, remaining close-only histories
  and other documented implementation/release gaps remain open. More complex membership and
  mixed billing/credit-memo histories still need end-to-end coverage. No deployment or claim
  of production readiness; independent accounting sign-off remains outstanding.

## Cross-member asset settlement from revenue returns — October 20, 2026

- Functional/reporting revenue returns can now settle another authorized group member's asset.
  The original signed posting replay identifies that asset owner and retains both sides of the
  settlement transfer. Asset settlement is never classified as opening-liability consumption.
- A new asset presentation bridge independently reconciles retained asset-layer carrying with
  presented contract-asset plus unbilled balances at each opening, closing and monthly endpoint.
  Creation, settlement and remeasurement amounts must match their original trace; member
  transfers and group endpoint differences must conserve zero. OTHER does not determine the
  adjustment. Every consumed layer and endpoint/source-transfer amount is bound for rerun.
- The revenue asset-source method is retained even when no transfer occurs, preserving scope
  on rerun. Earlier bindings keep their original method. Migration 0204 records the expanded
  report logic. Cross-member billing asset settlements still need their own source presentation;
  this change covers revenue-return settlements.
- The real combined foreign scenario recognizes revenue for two members and then returns the
  second member's delivery, settling the first member's asset at retained spot .84. The return
  generates GBP 45,360 of equal/opposite member transfers and zero opening-liability relief.
- Necessary checks passed: full-range and return-month-only functional/reporting outputs and
  identical reruns, the existing asset-to-new-liability return case, catalogue migration
  consistency, scoped lint and types.
  Mixed TIME/EVENT attribution, intercompany counterparts, remaining close-only histories and
  the other release gaps remain open. No deployment or production-readiness claim.

## Cross-period returns: asset settlement and new liability sources — October 20, 2026

- Original revenue attribution now presents the recognizing member's asset settlements and
  newly created liability sources as well as liability consumption and asset creation.
  Signed liability effects drive the member presentation bridge; newly created liabilities
  do not become opening-liability relief. Foreign-owner asset/new-liability sources remain
  refused until their separate transfer presentation is implemented.
- Bridge v5 includes cross-member relationships whose original consumption predates the selected
  range, so a return-month-only report retains the same original paid history as a full-range
  report. Earlier v1-v4 report bindings retain their scope and presentation path.
- Fixed S14 EVENT classification when a full return leaves zero cumulative transaction revenue
  but a nonzero functional amount from historical rates. A non-time-released obligation now
  keeps that amount in EVENT instead of incorrectly routing it into TIME because zero equals
  zero. This does not invent per-layer mixed TIME/EVENT attribution or repair old sealed journals.
- Real foreign combined scenario: USD 45,000 advance and USD 54,000 delivery produce GBP 43,470
  revenue, including GBP 36,000 original opening relief. A full September return at retained
  spot .84 reverses GBP 45,360, settling the asset and creating a new liability. Full-range net
  revenue is GBP -1,890; September alone reports GBP -45,360 and zero opening relief.
- Necessary checks passed: both currency views and identical reruns for full-range and
  return-month-only disclosures, the prior combined delivery/return sequence, catalogue
  migration consistency, 16 S14 checks, scoped lint and types.
- Migration 0203 describes the source method. Mixed TIME/EVENT source allocation, intercompany
  counterparts, foreign-owner asset settlement, remaining close-only histories and the other
  documented release gaps remain open. No deployment or production-readiness claim.

## Mixed liability relief and own-member asset revenue — October 20, 2026

- Functional/reporting cross-member revenue now accepts original sources that both consume
  another member's liability and create the recognizing member's own contract asset. The full
  posted revenue delta is verified; only liability-consumption sources must match retained
  owner/layer relief. Asset creation remains separately evidenced and is not opening relief.
- Presentation bridge v4 uses the verified total liability relief to correct local member
  replay that initially presents cross-member consumption as asset revenue. The amount comes
  from original source layers, never from OTHER. Opening/current-range relief, asset revenue
  and member transfers reconcile independently; original v1-v3 bindings retain their path.
- A real foreign-currency combined scenario consumes USD 45,000 of July advances and recognizes
  USD 54,000 in August, creating an asset for the excess. After the actual FX close, functional
  disclosure reports GBP 43,470 revenue and GBP 36,000 opening relief. Functional/reporting
  reruns retain their original source amounts. Catalogue migration 0202 describes this method.
- Necessary verification passed: the mixed-source scenario, existing multi-period delivery/return
  disclosure and reruns, catalogue migration consistency, scoped lint and types.
- Mixed TIME/EVENT source allocation remains open: S14 currently computes a proportional
  functional TIME amount without retaining per-source allocation. Do not infer TIME ownership
  from S12 source dates, which also represent EVENT revenue. Cross-owner asset settlement,
  new-liability reversal presentation, remaining close-only histories and other release gaps
  still need work. No deployment or production-readiness claim.

## Retained revenue history for close passes — October 20, 2026

- Real period-end passes now freeze revenue paid-line identities and both original currency
  amounts alongside the existing FX population. The populations are distinct and covered by
  the same immutable encrypted evidence file and hash; an empty revenue population is explicit.
- Revenue attribution reads original close-pass evidence before falling back to ordinary
  computation evidence. A close pass lacking the new revenue population is refused instead
  of treating absent history as zero. Ledger role, selected line and retained hashes remain
  checked; recursive original-owner attribution and both currency views use the shared reader.
- Necessary checks passed: a real close release retains all original group revenue lines and
  their transaction/functional amounts; the existing FX close remains immutable/idempotent;
  combined-member deliveries, returns and report reruns remain correct. Three integration
  scenarios and scoped lint/types passed. No deployment.
- This completes capture/reader integration, not all close revenue scenarios. A nonzero
  close-only revenue posting still needs an end-to-end attribution scenario; mixed TIME/EVENT,
  intercompany reversal and asset/new-liability presentation remain open, as do the other
  documented feature/release gaps and independent accounting sign-off.

## Transaction-currency revenue reversal disclosure — October 20, 2026

- Ordinary transaction opening-liability disclosure now attributes negative revenue through
  original signed transaction source quantities and recursively verified paid lines. Original
  layer creation dates identify opening consumption; the recognizing member is not capped by
  its own opening balance. Reversal groups still must reconcile their complete control path.
- The shared source projection retains signed integer coefficients independently of rounded
  functional amounts, so a zero functional source does not erase a nonzero transaction amount
  or reverse its sign. No inverse FX conversion is used. Original layer dates are reconciled
  across historical computations; attribution caches cannot mix currency views.
- Reversal method, source identities, creation dates, paid lines and evidence hashes are bound
  for rerun, with an explanatory footnote. Earlier bindings retain their original builder;
  intercompany transaction reversals retain the earlier path pending counterpart attribution.
  Migration 0201 updates the disclosure IPE description.
- Necessary checks passed: the real combined-member delivery/return sequence reports
  USD 58,500 transaction revenue and opening relief, alongside GBP 46,800 functional values;
  transaction, functional and reporting reruns match. Existing single-contract results and
  catalogue migration pass. Fifteen source/delta checks, including zero-rounded source signs,
  and lint/types pass. No deployment.
- Still open: intercompany reversal attribution, mixed TIME/EVENT source allocation,
  close-pass-only revenue histories, asset/new-liability reversal presentation, per-obligation
  opening consumption and complex membership/carry histories. Final release verification
  and independent accounting acceptance remain open; Reporting is not yet complete.

## Cross-member revenue reversals through original posting history — October 20, 2026

- Ordinary revenue attribution now reads original transaction targets and their separately
  retained functional amounts, projects original owner/layer sources, and recursively
  subtracts the exact sealed paid-line population. Original role, period, TIME basis,
  ledger fields, computation hashes and all target/paid/delta amounts must agree. A shared
  per-report cache avoids repeatedly replaying the same immutable paid history.
- Live functional/reporting rollforwards and opening-liability disclosures use this proof
  for ordinary cross-member revenue. Source-proven reversals are now accepted when the
  complete posted owner/layer relief population equals the retained consumed-layer history.
  Dependencies and signed movements are retained for rerun. Earlier bindings keep their
  original path; intercompany entries retain their prior calculation and reversal limits.
- Necessary public scenario passes: three deliveries across two periods retain the prior
  same-period posting; a subsequent return reverses the original opening-layer owner's
  revenue. GBP 50,400 falls to GBP 46,800 for both recognized revenue and opening relief.
  Functional and reporting views rerun identically. Catalogue migration 0200, lint and types
  pass. No deployment.
- Still open: transaction disclosure reversal attribution, mixed TIME/EVENT functional
  source allocation, close-pass-only revenue history, asset/new-liability source presentation,
  per-obligation opening consumption and complex membership transitions. This completes the
  tested ordinary liability-backed return path, not every negative-revenue scenario.
  Final release verification and independent accounting acceptance remain open.

## Revenue posting-delta evidence and reconciliation — October 20, 2026

- Added revenue-line evidence reading alongside the existing FX adapter. It verifies the
  line against exactly one original retained posting intent in transaction and functional
  currency, verifies the trace/output and sealed posting, and captures the original
  pre-computation revenue population by ledger cutoff. Later/current lines are excluded.
- Added exact source-level target minus prior target minus paid reconciliation, including
  TIME, EVENT and ALL bases, negative amounts and owner-preserving cancellation across
  computation versions. Target totals, TIME components, paid totals and final delta are
  each checked. Source date and source key now accompany the signed layer projection.
- Ordinary revenue posting trace nodes are transaction-currency nodes; their functional
  amounts are separately retained. The reconciler therefore accepts verified explicit
  target facts rather than treating the transaction trace as a functional FX delta.
- Necessary checks passed: 14 focused source/delta checks and a real combined-contract
  sequence proving the later revenue envelope includes the prior posting but excludes its
  own posting; incorrect functional amounts are refused. Existing report reruns pass.
- Still required: wire verified functional target/time projections and recursive paid
  attribution into report presentation, including close-pass revenue histories. This
  internal reconciliation/reader addition does not yet enable complete negative-revenue
  reports. Per-obligation opening consumption, asset presentation transfers and final
  accounting/release acceptance remain open. No deployment.

## Signed revenue calculation sources — October 20, 2026

- Added exact signed expansion of retained S12 revenue cumulative targets, preserving each
  original movement, owner, layer and kind. The reader handles liability consumption, asset
  creation, asset settlement and liability creation, including negative contributions and
  opposing owners at a zero net target. Every intermediate total must reproduce its trace;
  missing, duplicate, cyclic, changed-amount or wrong-currency sources are refused.
- Combined-member revenue attribution now verifies selected relief against the complete
  signed target. New runs retain the source projection and movement population for rerun;
  existing bindings retain their earlier validation path. This connects the source reader
  to live rollforward and opening-liability disclosures rather than a standalone calculator.
- Necessary checks: real cross-member functional/reporting disclosures and bound reruns;
  six signed-source/corruption checks; lint and types. No deployment.
- This is the source expansion needed for further posting-delta work, not completion of
  negative-revenue reporting. Original/prior target and paid-history reconciliation, asset
  presentation transfers, per-obligation opening consumption and complex carried histories
  remain open. Final release verification and independent accounting acceptance remain open.

## Reporting and forecast data catalogue reconciliation — October 20, 2026

- Classified the 43 missing code columns across retained evidence-sample dependencies,
  forecast actuals captures, scenario refresh records, ordered inputs and import replay
  mappings. Business payloads remain confidential financial data; identifiers and lifecycle
  metadata follow the existing registry rules. Existing retention categories are preserved;
  proposed classifications still require owner acceptance, not implied legal approval.
- Added the missing scenario-refresh model section and explicit sample dependency columns;
  documented frozen import mappings. The catalogue now matches all 174 documented tables
  and every implemented column. Updated the strict documentation reader for the existing
  four-column table format and reconciled document order.
- Snapshot checks now explicitly verify that copied imports clear the regenerated forecast
  input-set reference and source-only mapping without mutating source data. The recorded
  reference-count/excluded-column drift and privacy registry failures are resolved:
  76 targeted catalogue and snapshot checks pass. No database migration or deployment.
- Remaining Reporting work is unchanged: original negative-revenue reversal attribution,
  per-obligation opening consumption, complex cross-member asset/carried histories and
  pre-close FX paths. Final release checks and independent accounting acceptance are open.

## Transaction opening-liability group consumption — October 20, 2026

- Positive transaction RPT-04 now pools control flows by retained computation version,
  entity and currency, assigning actual opening-layer consumption to the recognizing
  member. Earlier credit-memo debits reduce the available opening layer. Opening holders
  remain visible even when another member recognizes the revenue; groups and source
  method are retained for identical reruns. Migration 0199 updates the IPE description.
- Necessary verification: the combined-member disclosure reports USD 54,000 opening relief
  for an August-start range and zero for a July-start range, with unchanged USD 54,000
  recognized revenue and identical bound reruns. Existing single-contract results pass.
  All 28 control-path unit checks pass, including credit-memo consumption before revenue;
  implementation lint and types pass.
- Negative transaction revenue deliberately retains the existing net-reversal calculation;
  original reversal-source attribution remains unfinished. Per-obligation consumption,
  cross-member asset-creating/carried/other-control histories, pre-close unposted FX paths,
  recorded registry gaps and final accounting/release acceptance remain open. Reporting
  is not yet complete. No deployment.

## Opening-liability disclosure in functional/reporting currency — October 20, 2026

- New functional/reporting revenue_from_opening_liability requests now consume the retained
  balance path and original opening-layer attribution instead of silently reading amount_txn.
  Reporting openings use preceding closing rates; revenue flows use their period averages.
  The method, source populations and rates are bound for rerun. Earlier bindings keep their
  prior builder path; the transaction view is still the separate legacy implementation.
- The disclosure includes opening holders and recognizing members without capping a
  recognizer's valid combined-group relief at its own zero opening. Its footnote explains
  that distinction. Member/period source paths must reconcile before the disclosure is
  emitted, so unmatched paths cannot silently become disclosure totals. The IPE catalogue,
  source contract and migration 0198 document the additional sources and currency semantics.
- Necessary public checks passed: standalone disclosure totals and contract details equal
  the corresponding functional/reporting rollforward relief in the combined-member case,
  including GBP 43,200 recognized against another member's opening. July-start versus
  August-start ranges change opening/current provenance without changing recognized revenue.
  Reporting currency, summary opening totals and identical bound reruns pass; lint/types pass.
  No deployment.
- Still open: the transaction disclosure's legacy same-contract cap, per-obligation opening
  consumption, cross-member asset-creating/reversing/carried/other-control histories and the
  underlying posting-delta replay gaps. This new disclosure path currently requires reconciled
  source balance movements; pre-close paths with unposted FX are not accepted. Recorded
  registry gaps and final accounting/release acceptance remain; Reporting is not complete.

## Cross-member revenue relief and opening provenance — October 20, 2026

- Added retained positive-revenue layer transfers for combined members. The original trace
  identifies the recognizing contract while the movement keeps the consumed layer's owner.
  All liability reliefs must reproduce the affected recipient's entire posted revenue in
  every selected period before any transfer is admitted. Original lines, relief/creation
  movements, amounts and opening portions are bound for rerun. No remainder is inferred.
- The v3 member bridge includes those source transfers and classifies revenue by the actual
  consumed layer's creation date, not the recognizing member's own billing history. v1/v2
  bindings retain their original paths. Migration 0197 updates the rollforward IPE catalogue.
- Necessary public checks passed: another member recognizes USD 54,000 revenue using GBP
  43,200 of the first member's July advance; differing historical-rate member closings are
  GBP 74,571.43 / 29,828.57 with +2,571.43 / -2,571.43 reclassification and zero OTHER. Functional,
  monthly reporting and bound reruns pass. An August-start range classifies the GBP 43,200 as
  opening relief; a July-start range classifies it as current-range relief without changing
  total revenue or closing balances. Scoped lint/types pass. No deployment.
- Still open: the separate revenue_from_opening_liability builder reads amount_txn and applies
  its legacy same-contract cap; it must consume the multi-currency/source-backed relief path.
  Cross-member asset-creating, reversing, carried and other-control histories need their own
  posting-delta replay; this path requires full positive liability-relief reproduction and
  refuses unmatched histories. Recorded registry gaps and final accounting/release acceptance
  also remain. This is not full Reporting or production-readiness acceptance.

## Endpoint-driven member liability presentation — October 20, 2026

- New functional/reporting builds apply the retained member-presentation bridge to all
  foreign contract/entity endpoints, including periods without a memo or FX journal. This
  explains historical-rate reallocations when another member adds billing. The v2 binding
  records entity-qualified endpoint identities; v1 reruns retain their memo-triggered scope.
  Cache and member selection now distinguish entities so one contract cannot borrow another
  entity's carrying or presentation evidence. Migration 0196 updates the IPE description.
- Necessary checks passed: an actual two-member group with USD 90,000 advances at GBP rates
  0.80 and 0.84, no credit memo and no FX journal. Both members close at GBP 73,800; the
  independently sourced reclassifications are +1,800 / -1,800, and both OTHER amounts are zero.
  Functional and reporting views across August–September and their bound reruns pass. The
  existing monetary multi-layer repeated-close/report flow also passes under the broader
  source scope. Scoped lint/types pass; no deployment.
- Still open: cross-member revenue/other control-flow source transfers, more complex carried
  EVENT corrections and membership transitions, recorded privacy/snapshot registry gaps and
  final accounting/release acceptance. Generalizing the endpoint trigger does not establish
  those separate source-flow cases or production readiness.

## Combined-member credit-memo presentation — October 20, 2026

- Functional billing now reads source layers across the report's authorized members of the
  same immutable group version and entity. A credit memo can therefore price a relief whose
  layer belongs to another member, retaining the real source owner and movement identities.
- Added a combined-liability presentation bridge for in-range cross-member memos. It computes
  each endpoint's original layer carrying versus the engine's member presentation, then adds
  the known memo issuer/source transfers. Each original computation group must conserve zero.
  The independently derived amounts appear as RECLASSIFICATIONS; no amount is inferred from
  OTHER. Bound endpoint facts, movements and transfers are checked on rerun, including monthly
  reporting-currency paths. Historical bindings without the bridge retain the previous path.
- Fixed a separate false-PASS: unexplained OTHER on an individual contract now fails the
  movement tie-out even when opposing contract errors cancel in the currency total. Migration
  0195 and the IPE catalogue describe the expanded source scope, bridge and per-contract check.
- Necessary checks passed: public two-member memo consuming another member's layer, same and
  different historical rates, exact member closing/reclassification amounts, bound reruns,
  reporting-currency monthly projection, 27 scoped path checks and lint/types. The differing
  rate case closes at GBP 74,314.29 / 41,285.71 with GBP +714.29 / -714.29 reclassification;
  every member has zero unexplained OTHER. No deployment.
- Still open: general member reallocations without an in-range cross-member memo, more complex
  carried EVENT corrections, recorded privacy/snapshot registry gaps and final accounting/
  release acceptance. These cases do not establish every membership transition or readiness.

## Locked-period foreign invoice carry — October 20, 2026

- The populated foreign lock witness now also follows the no-reopen path: an EUR 4,000
  invoice dated August is recorded after the actual August lock, then September is closed
  through the public pipeline. Transaction, functional and reporting rollforwards all pass
  their balance tie-outs. The August lock remains the only lock/reopen record for its period.
- Frozen opening remains EUR 10,000 / USD 11,050; closing after the carried invoice is
  EUR 6,000 / USD 6,720. September's actual FX pass supplies USD 70 of remeasurement. Before
  that pass the functional report correctly reported the unposted difference; no residual
  or synthetic balancing entry was added to hide it. This closes the ordinary invoice/TIME
  carry acceptance gap using the existing implementation. Reconciliation review fixtures
  remain fixtures, not independent approval; no external GL trial balance is claimed.
- Still open: public combined-contract credit-memo and more complex carried EVENT correction
  scenarios, recorded privacy/snapshot registry gaps and final accounting/release acceptance.
  Necessary verification is this actual lock/invoice/close/report flow plus scoped lint.
  No deployment and no claim that all Reporting or production readiness is complete.

## Credit-memo FX source attribution — October 20, 2026

- JET-10c attribution now resolves the original credit-memo difference trace into its
  retained liability reliefs, source owners, layer creation dates and event sequence.
  Each relief matches its original output and trace; the pinned rate and full difference
  formula are verified. Transaction portions are cumulatively converted in original trace
  order, preserving the once-rounded memo total and offsetting owner differences without a
  residual bucket or an allocation based on historical carrying value.
- Functional rollforward billing now uses the same retained spot conversion for those memo
  portions; actual posted EVENT FX adjusts each liability layer before its memo. Historical
  report bindings without the EVENT source path retain their former behavior. Derived source
  identities remain tied to immutable computation evidence and participate in paid-history
  subtraction. The engine and sealed journal amounts are unchanged.
- Necessary checks passed: actual single-layer and two-layer public memo/report workflows,
  ERP-imported and ENGINE-posted billing, source attribution and identical bound reruns. A
  USD 40,000 memo converts GBP 32,000 historical relief to GBP 33,600 at spot, with GBP 1,600
  FX and a GBP 40,000 closing liability. The two-layer full credit closes to zero with
  GBP 4,000 FX. Focused rounding/offsetting-owner and corruption checks, lint and types pass.
- Still open: public combined-contract credit-memo acceptance, late-carried public acceptance
  without reopening, recorded privacy/snapshot registry gaps and final accounting/release
  acceptance. This closes the ordinary JET-10c source gap, not every FX scenario. No deployment.

## Foreign lock-to-lock business attribution — October 20, 2026

- Difference replay now holds operational period states constant after verifying both original
  computations and frozen endpoints. A public reopen no longer blocks late-event attribution
  as an unsupported entity change. Entity, currency, book population and calendar dates remain
  strict; the evidence records entities.periods.states normalization and the final replay must
  still reproduce the later frozen money, including posted revenue.
- Control FX projection verifies the retained settlement formula when S12 emits a zero
  difference node without a movement row. It does not discard zero cumulative sums, so
  offsetting owners remain visible; altered rate evidence refuses.
- Necessary verification passed: actual foreign close/export/acknowledgement/lock, two-controller
  public reopen, EUR 4,000 late invoice, actual second close/lock, and public variance jobs in
  transaction, functional and reporting currency. Each attributes the asset reduction solely to
  LATE_EVENT (EUR 4,000 / USD 4,420 / EUR 4,000) and retains normalization evidence. Reviewed
  reconciliation rows are fixtures, not independent accounting approval. Scoped unit checks,
  lint and types pass. No deployment.
- Still open: credit-memo FX difference attribution (JET-10c has a retained difference trace
  but no remeasurement movement leaf), end-to-end late-carried public acceptance without
  reopening, recorded privacy/snapshot registry gaps and final accounting/release acceptance.
  This populated foreign two-lock witness does not establish every FX or membership scenario.

## Exact paid-origin window for carried FX — October 20, 2026

- TIME FX historical attribution now selects the target period plus its immediately preceding
  continuous closed/permanently-locked run, bounded by the retained anchor. It no longer treats
  every period between sparse calculation targets as paid: an intervening open period stops
  pooling, matching S14. EVENT/ALL retain their exact source origin. All period states come from
  the original encrypted computation input; today's calendar does not change reruns.
- Necessary verification covers sparse targets across an intervening open period, a retained
  anchor inside a locked run, EVENT origin isolation and refusal of TIME in a non-postable
  period; the existing actual multi-layer repeated-close/report scenario checks integration.
  Scoped lint/types pass. No deployment.
- Still open: end-to-end late-carried public acceptance, populated foreign two-lock acceptance,
  recorded privacy/snapshot registry gaps and final accounting/release acceptance. Correcting
  this selector does not establish those broader acceptance cases or production readiness.

## Regrouped FX source ownership — October 20, 2026

- Historical FX matching now uses S14's retained-membership regrouping rule. A stored group
  subject is compared under the computation's original member population; keyless legacy
  lines use that retained group/entity subject. Neither the sealed ledger fields nor the
  original source calculation is rewritten. Command intent checks retain exact stored subjects;
  only a missing subject uses the historical fallback.
- Necessary checks cover keyless settlement attribution, the actual reversal after the listing
  member leaves a three-contract group, and a two-contract public functional report. The latter
  assigns GBP 1,080 to the actual asset owner even though the ledger lists another member.
  The regrouping reversal retains the original paid-line dependency and delivered owner.
  The public August–September report after exit nets original/reversal/reposted FX to USD 200
  and passes the balance tie-out. Scoped lint/type checks pass.
- Scope correction: current control FX templates JET-10a/b/c select one role on each side;
  S14 does not emit split-weight targets for these flows. Unknown split formulas still refuse,
  but are not an outstanding feature for the current FX report path.
- Still open: late-carried public acceptance, populated foreign two-lock
  acceptance, recorded privacy/snapshot registry gaps and final accounting/release acceptance.
  Group settlement/exit cases do not establish every membership transition or production
  readiness. No deployment.

## Source-timed EVENT FX reporting — October 20, 2026

- Functional/reporting rollforwards now consume actual command EVENT posting deltas with
  original event sequence, source key, owner and asset/liability layer. Original and correcting
  postings net by dated source before walking the balance path. Billing settlement precedes
  its invoice; relief FX precedes revenue. New reports remove both old synthetic settlement
  movements, avoiding duplicate timing. Historical bindings retain the original path.
- New event_posted_fx_v1 bindings retain every command line, recursive paid dependency and
  evidence hash. Report execution rechecks its requester before authorized computation reads;
  close snapshots retain the restricted read-only SYSTEM path. Migration 0194 documents these
  source tables and semantics in the report IPE catalogue.
- Necessary checks: ERP and ENGINE foreign invoice rollforwards with source bindings and
  identical reruns; repeated liability close; command reversal and its net-zero report; scoped
  projection/path/catalogue checks and lint/types. No deployment.
- Still open: split-target formulas, regrouped/keyless historical subjects, combined-membership
  and late-carried public acceptance, populated foreign two-lock acceptance, recorded privacy/
  snapshot registry gaps and final accounting/release acceptance. These ordinary settlement
  cases do not establish production readiness or all Reporting requirements.

## Contract-computation FX evidence — October 20, 2026

- The shared FX attribution reader now adapts original command-computation input/output
  evidence as well as close-pass envelopes. It authorizes the complete retained group,
  verifies the encrypted source hashes, version trace and exact posting intent, and uses
  the original per-book seal cutoff to select historical paid lines. Version evidence keeps
  its real version identity; no synthetic close record or current-rate reconstruction is used.
- Paid attribution now follows actual command settlement and reversal histories recursively.
  Necessary checks passed: actual GBP 1,080 settlement and GBP 540 reversal with the original
  paid-line identity and both computation evidence hashes, plus scoped lint/types.
- Still open: public rollforward EVENT settlement timing must consume these sources without
  duplicating the existing before-invoice settlement flow and period-end offset. The TIME
  report path is unchanged. Split targets, regrouped/keyless historical subjects, combined
  and late-carried public acceptance, populated foreign two-lock acceptance, recorded registry
  gaps and final accounting/release acceptance remain open. No deployment or readiness claim.

## Mixed asset/liability FX sources — October 20, 2026

- Signed control-target attribution now admits retained contract-asset and liability
  remeasurement leaves, preserving role, owner, layer and creation date through prior-target
  and paid-history subtraction. Functional/reporting rollforwards direct asset FX to assets
  even with a live liability layer; liability FX remains layer-specific. Same-day closing
  corrections net per role/layer before application, so UUID ordering cannot overdraw a layer
  when a later close reverses an earlier remeasurement.
- New reports bind control_posted_fx_v2. Historical liability_posted_fx_v1 bindings preserve
  their original asset-path choice. Migration 0193 updates the report IPE source catalogue to
  name encrypted close-pass evidence and recursive paid-line attribution.
- Necessary checks: actual reporting-currency asset rollforward/rate change/rerun, actual
  repeated liability close and report source binding, snapshot producer/migration checks,
  36 focused catalogue/trace/path checks, scoped lint/types. Synthetic mixed-target checks
  verify opposite asset/liability signs and asset flows that must not consume liabilities.
- Still open: command-computation evidence adapters and paid attribution, split-target
  formulas, combined-membership and late-carried public acceptance, populated foreign
  lock-to-lock acceptance, the recorded privacy/snapshot registry gaps and final accounting
  acceptance. A synthetic mixed target is not a populated combined-contract public witness.
  No deployment or production-readiness claim.


## Historical paid FX and rollforward integration — October 20, 2026

- Close-pass evidence format 2 freezes the exact sealed FX control-line population read by
  the pass, including zero-net histories. The reader selects paid lines by retained role,
  currency, class, reason and origin/anchor periods, verifies their ledger fields and recursively
  resolves their retained close-pass deltas. Per-call memoization shares repeated dependencies;
  results bind every paid line and retained evidence hash. Format 1 remains readable but cannot
  establish automatic paid attribution; missing history refuses rather than allocating a plug.
- Functional/reporting contract-balance rollforwards now consume retained liability TIME
  deltas. Original creation dates keep opening/current-range layer identities, and group-level
  amounts follow source owners. New source bindings retain and recheck attribution dependencies;
  old bindings keep their original path. Asset-only FX remains on its existing path.
- Necessary checks passed: actual same-period second close after delivery, with nonzero prior
  paid amounts and explicit report source-binding assertions; original report rerun; the single
  liability close; ERP/ENGINE functional invoice paths; 25 focused projection/path checks and
  scoped lint/types. No deployment.
- Still open: command-computation paid adapters, mixed asset/liability target decomposition,
  combined-membership and late-carried public acceptance, populated foreign two-lock acceptance,
  recorded privacy/snapshot registry gaps and final release/accounting acceptance. Current tests
  do not establish completion of all combined/late-carried FX or production readiness.


## Signed liability FX posting attribution — October 20, 2026

- Added a signed trace projection from retained S14 targets through S12 cumulative sums to
  actual liability layer owners. The posting calculation subtracts the prior target and
  explicitly supplied attributed paid layers, distinguishes TIME from EVENT, and verifies
  every intermediate sum, retained time component, paid total and final journal delta.
  Missing/corrupt sources, unknown split formulas and unprovided nonzero paid history refuse.
- The internal close-pass reader now resolves a selected sealed FX control line to its unique
  retained delta by target, posting period, currency and amount. Its evidence adapter keeps
  source identities scoped to the immutable close record rather than inventing version rows.
  A real GBP 5,400 close-pass delta reproduces with its actual contract/layer ownership. Two
  synthetic two-owner cases verify TIME/EVENT subtraction, differing owner shares and refusal
  of missing paid/source evidence. Scoped lint/types and these necessary checks pass.
- Still unfinished: selecting/authorizing and recursively attributing historical paid lines,
  command-computation evidence adapters, wiring attribution into rollforward presentation and
  acceptance for combined/late-carried cases. No report-completion or production-readiness
  claim; no deployment. Registry issues recorded in the preceding checkpoint remain open.


## Retained close-pass calculation evidence — October 20, 2026

- Found the underlying CLOSE-PASS-TRACE-1 gap: actual close-pass ledger lines have no contract
  version/trace record. Latest contract traces cannot establish what an earlier pass posted.
  Revision 0192 now retains each actual pass's typed input, explicit pass name, selected book
  output, trace and selected line fields in encrypted storage, atomically with its sealed
  posting. Group entry indexes distinguish pooled postings. Source reads check file, logical
  input/output and trace hashes and the selected ledger line; historical absence stays absent.
- Added immutable tenant-scoped links, file ownership/retention holds, privacy classification
  and scenario regeneration rules. FX pass/idempotence, populated foreign public lock and
  automatic netting reversal checks pass; evidence remains after recomputation. Mutation and
  cross-tenant checks, 12 scoped file-registry/census checks, lint and scoped types pass.
- Not complete: reporting must consume this evidence and reconstruct attributed paid history
  for combined/late-carried liability FX; existing historical passes cannot be silently rebuilt.
  A broader registry check also exposed pre-existing unclassified evidence_sample_file,
  forecast_actuals_capture, scenario_refresh and forecast/import fields, plus stale snapshot
  reference-count/excluded-column expectations. Those remain release work (four checks fail
  after updating the regenerated-table census). No deployment or accounting acceptance.


## Currency exports in close evidence packs — October 20, 2026

- Close/re-lock packs now include functional and reporting CSVs for all six retained currency
  snapshot kinds, alongside the existing transaction paths. Snapshot identities retain original
  bundle hashes/counts and list each delivered view's path, hash, row count and control totals.
  Each export uses its retained column schema and spreadsheet formula guard. Historical
  single-view locks remain single-view; no current rates or live rebuilds are substituted.
- Targeted archive checks cover actual snapshot production, legacy locks, manifest/hash/count
  refusal and formula guards. Combined/late-carried liability FX and populated foreign two-lock
  acceptance remain outstanding. No deployment or production-readiness claim.


## Populated foreign-currency public lock — October 20, 2026

- The public lock witness now includes a EUR contract of a USD entity reporting in EUR. It runs
  actual close jobs and journal submit/approve/export/acknowledgement before requesting lock and
  obtaining a different Controller's approval. Frozen unbilled balances are EUR 10,000 in
  transaction/reporting currency and USD 11,050 functional. All monetary endpoints in all three
  views reproduce from the retained computation, after the source-read transaction closes.
- Reconciliation review rows remain test fixtures; this is not independent accounting approval.
  The domestic K01 public lock remains covered. This closes the single populated foreign-lock
  witness, not the still-outstanding two-lock foreign-currency report acceptance.
- Inspection for late liability FX found that S14 emits cumulative target differences and the
  ledger trace points to that target; fx_layer_key is not populated by the current product writer.
  The report's latest-version layer movements cannot simply be treated as those posted deltas.
  Next implementation must reconcile retained target/posted history and source-layer ownership;
  direct allocation from an assumed ledger layer key would be unsupported. Combined/late-carried
  liability FX remains unfinished. No deployment or production-readiness claim.

## Reporting-currency close variance — October 20, 2026

- The public variance report now offers reporting currency (migration 0191). Ordinary replay,
  connected membership changes and independent population changes use authenticated lock rate
  bases. Business effects use earlier reporting rates; a final FX phase applies later reporting
  rates after any transaction/functional FX phase. Identical retained computations with changed
  lock rates produce FX effects, never a fabricated business event or PROGRESS residual.
- Replay evidence retains both reporting-basis hashes and marks the reporting_rates phase.
  Entry effects are valued at earlier rates before FX; exits remove the earlier frozen value.
  Currency/period basis changes and missing historical rates explicitly refuse. New reporting
  waterfall snapshots retain the selected period's average even when there is no revenue, so
  later population comparisons need not read current reference settings.
- Necessary checks: real-engine business/FX and unchanged-computation cases, population entry,
  combined-membership reporting replay against authored frozen datasets, and public empty-lock
  jobs with bound reruns/revocation. Actual empty lock publication verifies retained averages;
  68 focused registry/rate checks, 96 frontend checks and scoped lint/types pass.
- Still outstanding: populated foreign-currency public lock-to-lock acceptance, combined and
  late-carried liability FX, other documented reporting gaps and final release verification.
  Older locks missing required currency/rate evidence cannot be silently reconstructed.
  No deployment or independent accounting sign-off; production readiness remains unproven.

## Retained reporting-rate projection — October 20, 2026

- Added a reporting-rate basis read only from verified WATERFALL, CONTRACT_BALANCES and RPO
  currency bundles. The basis binds source hashes and selected rate identities; balances must
  supply their own closing rate, conflicting retained conversions refuse, and nonzero revenue
  cannot borrow a closing rate when its average rate is absent.
- The replay projection now supports reporting amounts using per-line average revenue rates,
  separately rounded balance components, and sequential functional/reporting rounding of gross
  RPO and its exemptions per obligation. Original-source verification accepts this explicit basis.
- Necessary checks cover real-engine projected amounts and source reproduction, missing rates,
  corrupted snapshot hashes and conflicting metadata. A database witness reads all three actual
  snapshot producers and retains USD 11,000 -> EUR 10,000 revenue conversion. Targeted lint/types pass.
- This is the projection prerequisite: the public variance report still offers transaction and
  functional views only. Reporting rates must next be bound through each replay phase, with a
  separate reporting FX change (including unchanged engine inputs) and population/membership
  handling. Public reporting-currency variance, populated foreign lock-to-lock acceptance and
  the other documented gaps remain. No deployment or independent accounting sign-off.

## Functional close-variance attribution — October 20, 2026

- Variance between closes now exposes transaction/functional currency selection. The selected
  basis flows through frozen endpoints, ordinary groups, membership changes, population changes,
  driver totals and presentation. Functional source identity and cell evidence bind the currency
  choice; old transaction bindings retain their original form. Migration 0190 updates the stored
  report schema so existing repositories receive the selector.
- Foreign RPO replay now values each obligation from retained positive closing rates, rounding
  gross consideration and exempt amounts separately before subtraction. Missing/ambiguous rates
  and historical locks without the selected frozen view refuse; endpoint differences are never
  hidden in OTHER. A real-engine EUR example gives USD 79.51 of RPO FX movement, including
  per-obligation rounding, and conserves all replay endpoints.
- Necessary checks: populated real-engine group replay against authored frozen bundles; retained
  currency selection and missing-view refusal; database worker/reauthorization/bound-rerun on
  empty published locks; frontend fixtures and scoped lint/types. These are distinct witnesses,
  not a populated foreign-currency public-lock acceptance test.
- Remaining: reporting-currency close variance (not offered yet), populated foreign-currency
  lock-to-lock acceptance, combined/late-carried liability FX and documented release gaps.
  No deployment or independent accounting sign-off; the overall objective remains unfinished.

## Rollforward and disaggregation currency locks — October 20, 2026

- Extended immutable three-view lock storage, as-locked API/UI selection, CSV export and relock
  comparisons to contract balance rollforward, RPO rollforward and revenue disaggregation.
  Per-view schemas (including RPO translation rounding) and controls remain inside the hashed
  snapshot; report readers do not rebuild live inputs. Existing historical locks still refuse
  alternate views they never retained.
- Database checks cover each added report in all three views through API and exact CSV output
  with its live builder disabled, plus public empty/populated lock publication. A foreign-currency
  disaggregation witness retains EUR 10,000 transaction, USD 11,000 functional and EUR 10,000
  reporting revenue with rate evidence. Targeted fixture/unit checks, 94 frontend checks,
  frontend types and scoped lint pass.
- Remaining implementation includes close-variance currency selection and attribution against
  these snapshots, combined/late-carried liability FX and documented reporting/release gaps.
  No deployment or independent accounting sign-off; no production-readiness claim.

## Immutable currency views at lock — October 20, 2026

- Public lock publication now retains transaction, functional and reporting variants for
  waterfall, contract balances and RPO in one manifest-hashed machine CSV per dataset. Per-view
  columns, controls and available rate evidence are authenticated inside that same file.
- As-locked API, report viewer and exports select retained variants without live recomputation.
  Old locks remain readable on their original basis and explicitly refuse missing alternatives.
  Relock comparisons expose functional/reporting changes separately from transaction changes.
- Necessary checks: actual public lock publication and populated K01 balances; retained API/CSV
  selection with the live builder disabled; 62 focused Python checks and 94 frontend checks;
  targeted lint, types and frontend compilation. No deployment.
- Remaining: alternate-currency rollforward/disaggregation lock datasets and close-variance
  integration, combined/late-carried liability FX, and other release limitations. This checkpoint
  does not complete all four reporting workstreams or provide independent accounting sign-off.

Current snapshot-currency update (October 20): snapshot producers can now explicitly select
transaction/functional/reporting currency through their actual report schemas. Output controls
record the chosen view and historical cutoff; omitted selection preserves existing defaults.
Database witnesses cover waterfall/RPO conversion and the original-cutoff waterfall after later
rate publication. Lock publication still saves only default datasets, and as-locked currency
selection remains unfinished. This is a prerequisite, not completion of alternate-currency
frozen close integration. Other documented accounting/release gaps remain; no deployment.


Current contract-record update (October 20): ordinary and membership replay now phase retained
contract-record updates before application events, keeping identity, transaction currency,
contracting entity and inception fixed. A combined-contract legacy template bug found in the
monetary amendment witness is fixed: group reconciliation includes unchanged member allocations,
and the amended member receives the residual fixed-basis budget. Targeted legacy-template and
report replay checks cover ordinary/grouped paths and preservation of the other member's allocations/revenue/RPO; group balance attribution may change.
This supersedes the contract-record refusal below; basis migrations, missing sources, incompatible
prior bases, group-level posted redistribution, combined/late-carried liability FX and alternate
currency frozen close integration remain open. No deployment or independent accounting sign-off.


Current membership/estimate update (October 20): membership replay reconstructs the earlier
member/portfolio estimate set and introduces later approved versions before application events.
Historical versions cannot disappear or change contents. A real-engine merge + delivery + VC
revision witness verifies that membership keeps its isolated effect, an unapplied version has
zero effect, and application has a separate dated event contribution with retained source keys.
This supersedes the blanket estimate-record refusal below. Contract-header changes, inconsistent
earlier bases, missing members, group-level postings, combined/late-carried liability FX and
alternate-currency frozen close integration remain open. No deployment or accounting sign-off.


Current membership/reference update (October 20): merges/splits can now coexist with changes
to SSP/template/rule references and resolved accounting policies. Membership first uses prior
member policies and a coherent prior reference basis; a distinct OTHER phase applies later
references/policies before events and FX. Contract-scoped policies follow their members and
shared-policy conflicts are rejected. The real-engine witness combines merge, an RPO exemption
election and late delivery with independent phase and report/cell reconciliation. Contract and
estimate-record changes, incompatible prior bases, missing members, group-level postings,
combined/late-carried liability FX and alternate-currency frozen close integration remain open.
This supersedes the blanket mixed-reference refusal below. No deployment or accounting sign-off.


Current membership/FX update (October 20): membership and new business events now run on the
earlier coherent FX basis, followed by a separate later-rate FX phase. A real-engine witness
for two merged EUR contracts shows USD 60 functional revenue FX movement per contract and
independent phase reconciliation. Earlier groups with inconsistent FX bases remain refused.
The worker supports explicit functional projection; existing frozen datasets and the public
close-report currency selection are unchanged. Alternate currency lock datasets/integration,
mixed contract/reference changes, missing members, group-level posted redistribution and
combined-contract/late-carried liability FX remain open. This supersedes the mixed FX refusal
below. No deployment or independent accounting acceptance claimed.


Current mixed-membership update (October 20): group reorganization can now be followed by
new business-event phases in the same comparison. Membership runs first, then ordered driver
runs with late-event precedence. Exact phase amounts, source event keys and execution hashes
are retained, and the final state must reproduce frozen endpoints. A real-engine merge plus
late-delivery witness independently checks both effects and report/cell provenance. This
supersedes the business-event refusal immediately below; simultaneous contract/estimate record,
policy/reference or FX changes remain unsupported. Missing member sources, group-level posted
redistribution, combined-contract FX ownership, late-carried FX and full lock-flow acceptance
remain open. No deployment or independent accounting sign-off claimed.


Current membership-attribution update (October 20): isolated merges/splits of existing retained
contracts now produce verified group.membership contributions under MODIFICATION. Original
computations and frozen endpoints are reproduced, old groups are checked at the later cutoff,
and new groups replay on the earlier contract-qualified posting basis. Per-contract evidence
retains both actual group identities. Real-engine authored-frozen-dataset tests cover merge,
reverse split, presentation/cell provenance and refusal of a simultaneous delivery. Mixed
business/reference changes, missing earlier member sources and group-level posted redistribution
remain unfinished, as do combined-contract FX and late-carried FX. No deployment, full lock-flow
acceptance or independent accounting sign-off claimed.


Current liability-layer FX update (October 20): functional/reporting balance rollforward paths
now preserve billing layer keys and apply trace-verified per-layer FX, with relief FX before
revenue and closing FX afterward. Opening versus current-range billing classifications remain
intact. Layer movement totals must agree with posted period FX. The real API witness covers an
approved monetary override, three advances, close passes, subsequent delivery and retained rerun;
ERP/ENGINE invoice regressions pass. Combined-contract ownership and late-carried differences
without matching dated evidence still require work; this does not complete all variance or
release acceptance gaps. No deployment or accounting sign-off claimed.


Current RPO rollforward update (October 20): functional/reporting views now use monthly average
rates for business movements and dated closing rates for endpoints. The endpoints share RPO's
obligation-level gross/exclusion projection. FX and rounding are separate lines, and source
unexplained differences cannot be hidden by translation. Three-month API evidence covers FX,
endpoint ties and retained reruns after rate revision; an unsupported-source witness still
fails reconciliation. This supersedes the live RPO-rollforward currency limitation below.
Alternate currency lock datasets, multi-layer liability FX and group-change attribution remain
unfinished; no production readiness, deployment or independent accounting acceptance claimed.


Current RPO disclosure update (October 20): the RPO report now supports functional/reporting
currency using approved retained as-of closing rates. Gross/excluded translation and allocated
net rounding conserve bands, current/noncurrent and cell sources. Source rollforward comparison
is explicitly transaction currency. API witnesses cover rate revisions, retained reruns and
full exemptions; the projection witness covers partial-exemption cent rounding without source
mutation. RPO rollforward currency movement/FX attribution and alternate locked-dataset currency
views remain unfinished, along with multi-layer FX and group-change attribution. No deployment.


Current waterfall currency update (October 20): foreign-currency obligations now support
functional actuals and reporting actuals at retained posting-period average rates. Scheduled
and awaiting-trigger amounts use explicitly labelled as-of closing-rate forecasts; these are
not historical deferred-revenue layer valuations. Cells retain source links and converted
contributions; journal comparison stays in functional currency. Necessary API witnesses cover
actuals, forecast schedules, awaiting-trigger amounts and rate-revision/rerun behavior. RPO
currency views, multi-layer FX and group-change attribution remain open. Existing locked
WATERFALL datasets remain transaction currency. No deployment or production-readiness claim.


Current revenue disaggregation update (October 20): functional and reporting views now honor
the selected currency basis. Functional revenue comes from posted amounts; reporting uses
retained period-average rates, with line-level currency rounding and summed display totals.
Its journal comparison stays explicitly functional. New runs and retained reruns after a rate
change pass the targeted API journey; transaction behavior is unchanged. Older reporting bindings
without rate evidence cannot invent that evidence on rerun. This does not complete revenue
waterfall or RPO multi-currency coverage, or substitute journal comparison for external GL
reconciliation. No deployment.

Current targeted-VC adapter update (October 20): the production bundle now carries allocation
criteria from the estimate element, with no version-parameter substitution. Later RPO quota
changes read the same authoritative element evidence. A positive approved two-version journey
now covers net report amounts, cell contributions, the snapshot producer's single partially
exempt row, CSV export and retained rerun. This supersedes the earlier missing positive
partial-exemption report/snapshot/export witness for this supported path. It does not certify
all period-lock workflows, exemption combinations or broader multi-currency reports. Existing
stored computations are not rewritten; new computations receive the corrected source input.
No deployment.

Current original-duration exemption update (October 20): POL-197 in the report, rollforward,
dashboard and close-variance projection now uses original inception segments from verified
retained computation inputs. Extensions/shortening do not redefine the original term, and the
first-anniversary boundary matches the engine's inclusive dates. Live exemption detail shows
original start/end dates; new report bindings retain terms for reruns/cell explanations. Missing
source evidence or older bindings without terms are refused rather than inferred from current
end dates. This corrects the earlier current-term exemption behavior. Partial-VC populated
lock/export acceptance and broader RPO currency coverage still need completion. No deployment.

Current reporting rollforward update (October 20): contract balance rollforward now translates
monthly functional paths using preceding closing, monthly average and closing rates, with
separate TRANSLATION and ROUNDING lines. Original range-opening liability attribution persists
across months; retained rate/version facts reproduce old reports after new rates are published.
Functional OTHER remains a failed control even when translation rounds it away. Balance and GL
comparisons stay explicitly functional. This supersedes the older blanket reporting-rollforward
limitation for supported functional paths. Broader revenue/RPO currency coverage, monetary
multi-layer liability FX and combined-contract attribution remain incomplete. No deployment.

Current reporting-currency update (October 20): contract balances now translates functional
balances at approved closing rates into the tenant reporting currency. Exact currency rounding,
row totals, source rate/version retention and reruns after new rate publication are supported.
Locked endpoints use their frozen cutoff for rate admission. Tie-outs remain explicitly functional.
This supersedes the blanket reporting-currency limitation for contract balances only; reporting
rollforwards still need opening/flow/closing translation and separate translation differences.
Broader report coverage, multiple monetary liability layers and combined-contract attribution
remain open. No deployment.

Current functional rollforward update (October 20): contract balance rollforward now reads
functional opening/closing targets and functional flows. Historical invoice layers supply billing
in ERP and ENGINE modes; ENGINE billing must reproduce posted functional totals. Settlement FX
is timed before its invoice and removed from the period-end FX component without changing net
FX. Historical/locked balances, uploaded GL comparisons, both billing modes and retained reruns
pass targeted journeys. Multi-layer monetary-liability FX and combined-contract layer attribution
still need work; ambiguous multi-layer FX is refused. Reporting-currency translation and broader
multi-currency report coverage remain incomplete. Earlier blanket functional-rollforward refusals
are superseded for these supported source paths. No deployment.

Current population variance update (October 20): whole independent groups entering/leaving a
frozen population now receive explicit, source-verified contributions and drill-through. The
absent side has no synthetic computation. Entries use NEW_CONTRACT; departures remain OTHER
with population.left evidence, not a cancellation assertion. Regrouping and membership changes
inside an existing group remain unsupported, as do calendar changes. Earlier blanket statements
that all population changes are refused are superseded by this narrower supported path.

Current partial RPO update (October 20): POL-200 now reads dated targeted allocation/share
traces and immutable estimate eligibility, preserves fixed/untargeted consideration, apportions
net bands and reports the excluded portion. Dashboard, frozen obligation rows, rollforward
EXEMPTIONS movement and close-variance replay share this basis. Real-engine allocation/history
and performance-release checks pass; populated partial-exemption API/lock/export acceptance
remains. Older statements that POL-200 always excludes zero are superseded for supported traces.

Current functional balance update (October 20): contract balances now uses dated retained engine
functional targets, including historical periods and verified locked transaction endpoints.
GL reconciliation uses the same targets, and selected source versions are retained for report
reruns. EUR receivable August/September and locked-period/rerun journeys pass. Nonzero captions
without functional targets remain explicit refusals. Full functional rollforward movements and
reporting-currency translation remain outstanding; this does not complete multi-currency reporting.

Current reporting implementation update (October 20): close variance now evaluates changed
reference inputs separately from business events, then changed FX rates, retaining phase hashes
and changed fields. Group/calendar/population changes still need additional work. Contract balances and
balance rollforward now compare GL reconciliation role totals per entity and retains its source
facts for reproducible reruns. Missing/uncomparable sources remain NOT_APPLICABLE; any comparable
role mismatch fails even when aggregate differences cancel. Viewer and XLSX/PDF show details.
This does not complete foreign-currency rollforward valuation, all GL source coverage, population
replay or dated POL-200 exclusions. POL-199 can legitimately exclude zero because royalty amounts
are realized when reported; zero alone is not proof of an unimplemented exemption. No deployment.

Current Tamsin acceptance/fix (October 19): the real-template, approved-H2 SSP case now matches
95,200/22,000 selected SSP, below/above flags, 94,225.26/21,774.74 allocation and November 2026
revenue start. The test exposed missing schedules from the booking-only DRAFT bundle. New deal
previews retain a hypothetical inception activation in DRY_RUN evidence only; no production
contract/event is activated. Simulated cumulative revenue is displayed alongside scheduled and
awaiting amounts. Old previews remain unchanged. Browser and independent accounting acceptance
are still open; the prior generic empty-schedule explanation did not prove this subscription case.

Current preview history update (October 19): SF-18 now lists retained previews in the caller's
entity scope, pages older results, and links to retained calculations and saved drafts without
replacing current form input. Request/save completion refreshes this metadata list. This closes
the history navigation gap; browser/business accounting acceptance and independent sign-off
remain open. No deployment.

Current forecast metadata update (October 19): the assumption manager now creates, edits and
clears optional UTC effective windows, displays saved boundaries and requires saving before
publication. These are version metadata; no claim is made that they filter captured replay
facts. Published records remain immutable. Other reporting acceptance and independent accounting
sign-off remain open. No deployment.

Current scenario refresh correction (October 19): the UI now releases acknowledged request
identities and follows subsequent durable refreshes, including a newer refresh observed after
an accepted job has completed. This removes an indefinite-wait/blocked-submit state. The
variance_between_closes builder/replay/presentation already exist; broader business acceptance
and independent accounting sign-off remain unproven. No deployment.

Current deal product selector update (October 19): new proposal entry now offers searchable
active products by code/name, loads subsequent catalogue pages, and requires a selected product
on every line. Retained preview reads do not depend on loading the current catalogue. Product
selection is implemented; real browser/Tamsin acceptance, independent accounting sign-off and
remaining report gaps are still open. No deployment.

Current scenario save UI update (October 19): SF-18 now exposes server-qualified save eligibility,
external-ID entry, retry with retained input, and a link to the saved draft. Reopening a saved
preview keeps the link and does not offer another save. Real scenario and production journeys
verify eligibility changes and refusal; the write command independently rechecks authorization.
Product picker, real Tamsin/browser acceptance, other report gaps and independent sign-off remain
open. Earlier statements that the save button is absent are historical. No deployment.

Current deal save update (October 19): scenario-only POST /deal-previews/{id}/save now creates
one normal DRAFT contract from verified preview evidence, with current contract permissions,
configuration validation, suggestions and holds. It requires an active registered scenario and
refuses production saves and duplicate saves. Real scenario/API journeys pass; the UI save
control is still absent. Independent accounting sign-off and full FCS-6 acceptance remain open.
Reporting clarification: actual_vs_forecast has a builder, retained source logic and UI; the
populated K11 item is an outstanding acceptance exercise, not a missing report implementation.

Current deal revenue update (October 19): SF-18 now includes product/period totals and a signed
revenue chart, with separate entity/currency scopes and 24-period paging. All-period totals
remain visible across pages and use exact decimal arithmetic. Awaiting-trigger amounts remain
outside period totals. Scenario save, product picker and Tamsin/browser acceptance are still
open, as are the other Reporting gaps and independent sign-off.

Current deal screen update (October 19): SF-18 now supports proposal entry, asynchronous
calculation, reconnect by job URL, saved preview reads, allocation/SSP and revenue tables.
This is the first functional screen, not full FCS-6 acceptance: scenario save, product selection
polish, revenue chart/period totals and Tamsin/browser acceptance remain outstanding. Other
Reporting gaps and independent sign-off remain open. No deployment was performed.

Current deal presentation update (October 19): verified detail reads now include structured
allocation/SSP range data, per-book totals and indicators, and revenue by entity/period/subject.
Scheduled and awaiting-trigger totals distinguish an empty schedule from a zero-value deal.
All values derive from retained engine evidence. The SF-18 screen and scenario save are still
unfinished; this is not completion of the Reporting workstream or Tamsin accounting acceptance.
Earlier notes describing absent result projection are historical.

Current deal API update (October 19): asynchronous POST /deal-previews and the DEAL_PREVIEW
worker now retain real engine results. Scoped list/detail reads and fingerprint checks are
implemented, with job-subject migration 0189. Scenario save, user-facing result projection
and SF-18 remain unfinished. The end-to-end fixture is not the required Tamsin accounting
acceptance or independent sign-off. Earlier notes describing absent worker/read APIs are history.


Current deal retention update (October 19): an idempotent domain service retains canonical
proposal/bundle/result evidence, engine release, reference pins and one run audit. It verifies
existing hashes and rejects changed input under the same identity. Worker/request/read APIs,
result projection, scenario save and UI remain absent; this service is not yet user-accessible.


Current deal bundle update (October 19): authorized proposal assembly now reuses ordinary
booking and reference-resolution rules inside a rolled-back scratch transaction. Successful
and failed assembly retain no temporary contracts/customers/audits; synthetic input identity
is reproducible within the same reference cutoff. Sequence gaps can remain after rollback.
Worker/API retention, result shaping, scenario save and the deal-preview screen are still absent.


Current deal-preview foundation (October 19): request schemas and a pure DRY_RUN engine
boundary now exist. The boundary preserves full engine output and verifies fingerprints,
rejecting posted baselines. This is not yet exposed as a product feature: authorized bundle
construction, audited worker/API persistence, result presentation, scenario save and UI remain
unimplemented. The required Tamsin example and independent accounting acceptance are outstanding.


Current direct forecast capture update (October 19): delivery/progress/milestone/cost/return
forms can explicitly target a draft assumption set in an authorized scenario workspace.
They use the existing atomic event-capture API and preserve contract/evidence validation.
Normal event approval is the default. Usage/invoices use forecast imports. Historical statements
that all direct event capture lacks UI are superseded; broader accounting acceptance remains open.


Current captured-input review update (October 19): assumption versions now show retained
contract-event bodies and import-source links in recorded application order. Numeric strings
retain their precision. Missing sequence evidence is reported instead of inferred; linked
current records are distinguished from captured inputs. Import-row detail remains in the
existing authorized import viewer. Direct event-entry capture and accounting acceptance remain open.


Current forecast import update (October 19): draft assumption records now open a targeted
import workflow. The upload page verifies and identifies the draft, restricts supported fact
templates, and preserves the association through corrected-file uploads. Import validation
and commit still govern attachment. Direct command capture and detailed input review remain
open; earlier blanket statements that import selection has no UI are superseded by this entry.


Current assumption lifecycle update (October 19): forecast page now supports draft creation,
name editing, publication confirmation and paginated version inspection. Published versions
are immutable and refresh the report input selector. Business-change capture UI, import
attachment selection, effective-date editing and detailed input review remain unfinished.
Lifecycle controls alone do not establish complete assumption authoring or accounting acceptance.


Current scenario reporting update (October 19): source workspace scenario creation, archive,
status filtering and refresh UI are implemented. Refresh selects published assumptions and
tracks durable outcomes, preserving the current copy on failure. Published-input metadata and
refresh history are source-authorized reads. Assumption authoring/publishing UI, deal preview,
populated accounting acceptance and independent sign-off remain open. Historical notes below
must not be interpreted as the current implementation inventory.


Current disclosure implementation correction (October 19): older entries below, including
recent register notes, incorrectly carried forward pre-implementation limitations. Current
code already captures sixteen inputs at the close cutoff, atomically publishes seven locked
snapshots, and rebuilds JSON/XLSX/PDF from verified frozen evidence. See disclosure_freeze.py,
disclosure_lock.py, disclosure_frozen.py and the archived atomic-publication/frozen-execution
entries. The register now also supports server-side DRAFT/LOCKED filtering before pagination.
Full populated accounting acceptance, independent sign-off and broader release verification
remain outstanding. Older dated descriptions are history, not the current feature inventory.


Latest disclosure register update (October 19): /reports/disclosures now lists authorized
snapshot metadata by entity, book, period and disclosure type, pages older records, and opens
verified retained detail and original report runs. Draft/locked source is displayed; source-status
filtering is not implemented. Lock-time capture and as-locked disclosure orchestration remain
open; the new register does not establish populated accounting acceptance.


Latest snapshot read update (October 19): disclosure snapshot list/detail APIs now support
scoped metadata pagination/filtering and verified retained evidence. Drafts are explicitly
labelled and source-parent attachment/scope is checked. Real API and permission-scope checks
pass. Lock-time capture, as-locked execution and a dedicated snapshot register UI remain open.


Latest disclosure snapshot update (October 19): draft report success now atomically retains
seven immutable E-65 snapshot records with original child/policy evidence. Draft records have
no lock ID and cannot substitute for lock-time capture. Lock-job integration, snapshot read
APIs and as-locked disclosure execution remain incomplete; no locked-period support is claimed.


Latest quarterly disclosure update (October 19): six displayed flow inputs now receive
period/QTD comparison summaries in JSON/viewer and chapter Excel/PDF exports. Original tables
remain available. Semantic identities include currency; missing rows remain blank with presence
flags. Real parent/rebuild and workbook checks pass; PDF wide-table readability, full browser
acceptance, populated accounting acceptance and frozen snapshots still require completion.


Latest disclosure viewer update (October 19): the report page now displays chapter/table
metadata and loads expanded tables from saved JSON through scoped, paginated report reads.
Omitted tables show notes without requesting amounts; money columns identify currencies.
Targeted component and real API pagination checks pass. Full browser/accessibility acceptance,
frozen snapshots, side-by-side quarter presentation and populated accounting acceptance remain.


Latest disclosure update (October 19): draft disclosure_pack creation, job execution,
JSON download and retained-input rerun now work through the standard report API. Only one
entity, ASC606/IFRS15 and an explicit period open at the source cutoff are admitted. Frozen
snapshots, the chapter viewer, side-by-side quarter layout and populated accounting acceptance
remain unfinished. XLSX/PDF rendering is connected but worker export journeys remain to verify.
There are now 55 registered report execution paths (54 single-table builders plus this composed
worker); actual_vs_forecast, forecast_outputs, contract_sample_pack and period_evidence_pack
remain unregistered. Older dated counts below describe earlier implementation stages.


Latest update (October 19): RPT-42 is now registered in the standard report worker with retained
input reruns and current initiating-user/API-client report/export permission checks. CSV export
and rerun were exercised after real imports for identity and renamed mappings; these dry-run
imports have no actual posted population, so the verified output is empty. Populated comparisons,
XLSX/PDF rendering journeys, cross-tenant sandbox/replay migration and complete LMG-5 accounting
acceptance remain open. Five catalogue builders remain unregistered: actual_vs_forecast,
forecast_outputs, contract_sample_pack, period_evidence_pack and disclosure_pack.


Latest reporting update (October 19): parallel comparison capture now binds its currency to
hash-verified original migration inputs and resolves post-cutover ranges through recorded open
period states. Full snapshots and requested boundaries are retained for replay. Calendar definitions
are resolved at capture time. Worker/export registration and publication authorization remain
unfinished, as do replay migration and sandbox lifecycle; this is not a completed RPT-42 release.


October 19 migration source admission update: original import operation/mapping, source file
hash and retained history rows are now checked under complete mapped-entity report permission.
Identity and renamed-entity imports pass, while incomplete scope and altered file bytes refuse.
This supports same-tenant full-source admission only. Partial-entity comparisons, replay-sandbox
authorization, full retained rebuild and worker/export registration remain outstanding; RPT-42
is still unregistered and the complete migration acceptance has not been established.

October 19 eRev comparison input update: an entity-authorized reader now supplies historical
journal facts and standard traced/frozen contract balances with retained source references.
A real computation/ledger case matches the existing gross journal view; unavailable contract
populations withhold period coverage. Migration source admission, mapping, complete binding and
worker/export integration remain open. This does not authorize cross-tenant sandbox reads or
complete the still-unfinished migration replay lifecycle; RPT-42 remains unregistered.

October 19 legacy comparison input update: an independent history projection now reproduces
all ten archived Jan–Oct 2023 gross journal exports and derives period-end contract positions.
Its source currency must have two decimal places, mappings must be complete, and contracts
spanning mapped entities refuse. It does not authorize or load a migration by itself. Report
source admission, eRev data selection, binding and worker integration remain outstanding;
migration replay import is also still unfinished. RPT-42 remains unregistered.

October 19 parallel-run comparison phase: exact comparison of supplied independent journal and
balance snapshots and the two viewer sections are implemented. Legacy monthly-output reading
with original rounding, authorized eRev source selection, retained binding and worker registration
are still required. Explicit source-fact checks are not command-driven LMG-5 financial acceptance.
Six catalogue builders remain unregistered, including parallel_run_comparison.

October 19 engine true-up register update: revision 0180 now exposes exact-cutoff processing
portions and actual attributed sealed ledger lines through JSON/CSV/XLSX reports. Same-source
reruns rebuild from retained input facts; current worker grants apply. This supersedes earlier
statements that this register is unimplemented/unseeded. Six other catalogue builders remain.
Full upgrade lifecycle and deferred-period reopening/cross-entity browser acceptance are still
open; the register does not complete those workflows or constitute accounting sign-off.

October 19 variance header/totals update: both lock IDs/timestamps, frozen-comparison source
labels, separate metric/currency totals and identical-lock empty copy are implemented.
Earlier header/empty-state limitations below are superseded. Six other catalogue builders and
engine_trueup_register still need development; populated close/cell/browser financial acceptance
and wider reference/FX/population replay remain open. No deployment or readiness claim.

October 19 variance cell/viewer update: Change cells now expose retained contract effects,
events and lock/source-row references through optional plain-text contributor details. The
viewer separates the two numeric sections; exports retain readable labels. Bound computation
membership and source identity/hash/scope checks remain required. Same-source reruns refresh
derived explanations. HTTP/DB cell and populated close/browser acceptance still need evidence;
headers/empty states and broader reference/FX/population replay remain unfinished. Six catalogue
builders remain unregistered. No deployment or production readiness claim.


Current reporting update — October 19: variance_between_closes is now registered and runs
through phased source loading, transaction-free computation and reauthorized output publication.
Source-bound reruns recompute from original evidence. A seeded empty-lock workflow exercises
actual jobs and stored outputs; post-compute permission loss prevents publication. This does
not establish populated close financial acceptance, cell explanation/UI completeness or support
for all reference, FX and population changes. Six catalogue builders remain unregistered:
actual_vs_forecast, forecast_outputs, parallel_run_comparison, contract_sample_pack,
period_evidence_pack and disclosure_pack. engine_trueup_register remains separately outstanding.
Earlier dated reporting entries below describe the implementation stage when recorded.


October 19 variance presentation: driver/contract sections, exact currency/measure totals and
contributor evidence now feed the standard export writers. Original lock/file/computation
identities, replay hashes and event/source-row contributions remain attached. This is not a
registered report: the worker still needs separate authorized-read, transaction-free-compute
and reauthorized-publish phases, followed by source-bound reruns, cell routing and UI. Wider
replay phases and full close accounting acceptance remain open; seven builders are unregistered.


October 19 multi-group variance continuation: authorized retained groups now replay against
partitioned frozen monetary endpoints and aggregate exact totals by currency, measure and
driver. New own-pricing SSP readbacks are accepted only when they preserve the earlier
reproduced output's SSP selection; actual first recomputation now reconciles. Other reference
changes, modification-weight readbacks, FX and population changes still need replay phases.
Report/job/formats/UI and full frozen-close accounting acceptance remain outstanding; seven
builders remain unregistered. No deployment or production readiness claim.


October 19 retained variance execution: original computation hashes and monetary endpoints
are verified before replay on a common earlier posting basis; normalized fields and source
identities are retained. Identical source computations yield zero change. First recomputation
can add recorded SSP policies and still requires the reference replay phase. The real-engine
carried-posting case and database source reuse pass targeted checks; group aggregation,
report/job/UI, broader replay phases and frozen-close accounting acceptance remain unfinished.
Seven report builders remain unregistered; this is not a completed RPT-38 report.


Forecast input-set update: version creation, metadata editing, listing, retrieval and immutable
publication APIs now exist in registered scenarios. They retain ordered input fields but do
not yet attach committed imports or record successful business commands. Input replay, refresh,
forecast execution/output and UI remain unfinished; FCS-2 is not complete. Scenario publication
uses its own audited lifecycle without a production approval request (T-FC-02, migration 0179).

Scenario archive update: creator/Controller archive now preserves sandbox reads and gates
HTTP business writes and worker attempt units of work through the source scenario status.
Pending jobs block archive; late worker writes fail while job settlement remains available.
Migration 0178 freezes archived scenario fields. API/worker acceptance covers empty-business
scenarios, not all concurrent/custom-write paths or nonempty/closed-period copies. Refresh,
event sets, forecasts, reporting output and the scenario UI remain unfinished.

Scenario creation update: POST /scenarios now drives the snapshot worker, copies a sandbox,
adds minimum creator access when absent from the historical snapshot, and registers/audits the
scenario. Actual worker acceptance covers empty business data and both membership cases.
Archive/refresh, nonempty contract/closed-period acceptance, worker interruption boundaries,
forecast input/execution/output and UI remain outstanding. FCS-1 is still incomplete.

Scenario catalogue update: GET /scenarios is now implemented with tenant isolation and status
filtering. Creation, archive, refresh, forecast execution and forecast report builders remain
unimplemented. Revision 0177 allows the pointer replacement required for future refresh while
retaining the source-tenant guard. No end-to-end forecast workflow is claimed.

October 19 actual FX correction: BBR's live and retained rate readers now match E-51's lowercase
`spot` via RateType.SPOT.value. The previous uppercase literal excluded real approved spot rates;
the old retained-input unit fixture did not catch it. Actual approved v1/v2 database rates now
verify current and historical valuation and version identity. This does not yet prove an entire
cross-currency contract-to-report journey or independent accounting acceptance.

Forecast dependency clarification: forecast_outputs and actual_vs_forecast lack their upstream
scenario workflows and forecast domain execution (FCS-1 to FCS-3), not just rendering.
Migration 0176 now supplies the four forecast tables and database guards; APIs, replay, jobs
and output builders remain absent. This does not complete FCS-1 or either forecast report.
They cannot be completed by substituting current actuals. Seven catalogue builders remain missing,
with this broader subsystem still outstanding. No deployment or production readiness claim.


October 19 BBR cell continuation: all four money columns now expose retained contribution
lists through the report-cell endpoint. The UI shows source IDs and links to contract history,
billing, modification detail or contract journals. These links open the relevant record view;
history/billing/journal links do not select an individual source row automatically. Existing
runs without the new aggregation evidence refuse explanation. Actual revenue/new-booking/billing
cells are exercised; a modification-cell journey, narrower-reader scope acceptance and live
browser navigation are still owed. Seven catalogue builders remain unregistered. Accounting
sign-off and the other BBR limits below remain open; no deployment/readiness claim.


October 19 BBR delivery continuation: bookings_billings_revenue is registered and runs through
the report API/worker with fiscal buckets, retained reruns and historical journal-revenue
comparison. Functional contract/billing contributions use a unique historical approved spot
rate on their effective day; revenue retains posted functional amounts. Missing/ambiguous FX
refuses. Seven definitions still lack registered builders: actual_vs_forecast, forecast_outputs,
parallel_run_comparison, variance_between_closes, contract_sample_pack, period_evidence_pack
and disclosure_pack. BBR's cell contributor routes, reporting-currency/lock datasets, complex
attribution and broader scenario/browser acceptance remain unfinished. Standard XLSX/PDF writers
are wired by the framework but not individually verified here. Independent approval of the
contract-value and spot-rate metric basis is still required. No deployment/readiness claim.


October 19 BBR attribution continuation: activated bookings now use the contract's signed
stated line consideration (not its group's allocated transaction price), with original event
provenance. Separate-contract modification bookings are excluded from the new-contract column.
Applied modifications use their historical application group's version minus its predecessor,
once per modification. Missing/ambiguous sources and shared valuation causes refuse; mutable
modification rows changed after the requested cutoff also refuse. Pre-activation amendments,
shared-cause attribution and broader cross-entity/separate-contract acceptance remain open.
FX valuation, journal source comparison, contributor routes and report registration remain
unfinished. Eight reports still lack complete registered builders. The booking metric basis
and the finished report still require independent accounting sign-off.


October 19 BBR implementation continuation: source capture and fiscal presentation now exist
for bookings_billings_revenue. Billing follows existing invoice identity/credit/void rules;
revenue uses sealed lines with server capture cutoffs and posting-period attribution. The report
is not registered: booking and modification valuation, governed FX, journal source selection,
contributor routing and final API/output integration remain unfinished. The count remains eight
reports without complete registered builders. Functional amounts are never inferred from
transaction amounts when currencies differ. No production-readiness or deployment claim.


October 19 contract reporting continuation: `extract_contracts` now exports captured headers
and historical customer/entity codes, with JSON/CSV, creation-time incremental selection and
retained inputs for reruns. Migration 0174 adds atomic, append-only source revision capture and
migration-time baselines. Coverage before initial capture is refused; capture timestamps do
not establish historical transaction commit visibility. Sandbox restores begin new coverage.
All nine data extract builders now exist. Eight catalogue builders remain: actual_vs_forecast,
bookings_billings_revenue, contract_sample_pack, disclosure_pack, forecast_outputs,
parallel_run_comparison, period_evidence_pack and variance_between_closes. The separate
engine_trueup_register, locked extract datasets, automatic watermarks and browser acceptance
remain unfinished. No deployment or production-readiness claim.


October 19 journal reporting continuation: `extract_journal_lines` now exports source-time
journal detail, resolving cancellation through stored times and audited lifecycle evidence.
It retains source rows and state evidence for reruns, with CSV/JSON and per-functional-currency
debit/credit totals. Migration 0173 updates source disclosure. Nine catalogue definitions still
lack builders (also remove extract_journal_lines from earlier lists); extract_contracts is the
remaining data extract. Locked datasets, watermarks, true-up and browser acceptance remain open.


October 19 legacy reporting continuation: `extract_legacy_contract_live` now exports all-date
ASC606 history in the established 71-column layout, with source creation cutoffs, incremental
selection, exact trace inputs and retained current/predecessor inputs for reruns. Migration
0172 updates query-source disclosure. There are now 10 catalogue definitions without builders
(also remove extract_legacy_contract_live from earlier lists). Contract and journal-line
extracts, locked datasets, watermarks, true-up and live browser acceptance remain unfinished.


October 19 subledger reporting continuation: `extract_subledger_lines` now exports sealed
line detail with business/server recording cutoffs, a server seal cutoff, retained labels,
JSON/CSV output and entity/book/currency/period control totals. Migration 0171 reconciles the
disclosed query sources. There are now 11 catalogue definitions without builders (also remove
extract_subledger_lines from earlier lists). Incremental selection is by business recorded_at,
not commit time; late sealing/commit of older records is not an automatic change feed. Three
extract builders, locked datasets, watermarks, true-up and live browser acceptance remain open.


October 19 balance reporting continuation: `extract_balances` now exports latest per-contract
balance rows with entity/contract labels, full/incremental source windows and retained-source
reruns. Contract-liability, contract-asset and unbilled-receivable control totals are grouped
by functional currency. There are now 12 catalogue definitions without builders (also remove
extract_balances from earlier lists). Four extract builders, lock snapshots, automatic
watermarks, true-up reporting and live browser acceptance remain unfinished.


October 19 schedule reporting continuation: `extract_schedule_lines` now exports latest
per-contract schedule rows with line-entity scope, period labels, precise values, per-currency
amount totals and retained-source reruns. There are now 13 catalogue definitions without
builders (also remove extract_schedule_lines from the earlier lists). Five extract builders,
lock snapshots, automatic watermarks, true-up reporting and live browser acceptance remain open.


October 19 obligation reporting continuation: `extract_obligations` now exports latest
per-contract versions with full/incremental windows, retained source rebuilding, all source
columns except tenant_id/trace_nodes, and per-currency allocation/revenue control totals.
There are now 14 catalogue definitions without builders (also remove extract_obligations
from the earlier lists). Six extract builders, lock snapshots, automatic previous-run
watermarks, true-up reporting and live browser acceptance remain unfinished. Incremental
obligation output is a latest-population snapshot delta, not a deletion feed.


October 19 contract-version reporting continuation: `extract_contract_versions` now has a
v1 full/incremental builder, retained-source reruns and JSON/CSV delivery. Membership comes
from the original computation; partial combined-entity selections refuse group totals.
Migration 0170 updates the report's disclosed query sources. There are now 15 catalogue
reports without builders (remove extract_contract_versions from the earlier list below).
The other seven extract builders, locked extract datasets, previous-run watermark defaults,
true-up reporting and live browser acceptance remain open.


October 19 reporting continuation: `extract_events` now has a scoped v1 builder, full and
incremental windows, retained-source reruns, JSON/CSV output, CSV manifests and page controls.
There are 16 catalogue definitions still without builders: actual_vs_forecast,
bookings_billings_revenue, contract_sample_pack, disclosure_pack, extract_balances,
extract_contract_versions, extract_contracts, extract_journal_lines,
extract_legacy_contract_live, extract_obligations, extract_schedule_lines,
extract_subledger_lines, forecast_outputs, parallel_run_comparison, period_evidence_pack,
variance_between_closes. This count does not include remaining work inside registered reports.
Extract lock snapshots and automatic previous-run watermark selection remain open. The event
extract uses recorded timestamps; it does not resolve the separate historical commit-visibility
gap. Live browser acceptance remains open. The upgrade true-up register is also unfinished.


October 19 upgrade continuation: accepted upgrade computations now persist attribution and
portion outcomes atomically with their postings, with retained-input integrity checks and
idempotent replay. Final acceptance and independent approval now have domain commands and existing approval
API integration. Tenant creation now distinguishes empty bootstrap tenants, historical tenants
and skipped release levels. A permission-guarded API resumes replay, report attachment and
acceptance from durable state. Autonomous scheduling, explicit baseline preparation,
the computation gate, true-up register and runtime closed-period/rescheduling verification
remain open. The advancement API requires successive caller requests; it is not a background driver. Scoped evidence is in [the October 19 CI record](CI-2026-10-19.md).

Historical subledger cutoff work (October 15): migration 0151 adds a database-owned
insertion timestamp to new sealed lines. Explicit historical reads use that timestamp;
record/current/close reads retain the application timestamp. The focused regression now excludes
a later insertion even when its transaction began before the cutoff and its application clock
is earlier. This is not proof of historical commit visibility: a transaction that inserts before
a cutoff but commits afterward remains a separate gap. Migration 0152 adds a database-owned
sealing timestamp: historical reads additionally require that the complete posting was sealed by
the cutoff, so a cutoff between its lines cannot expose only part of that posting. This does not
establish transaction-level commit visibility. Seals are tenant-scoped; line/entity scope remains
on the outer read, so hidden sibling lines cannot make an incomplete posting appear complete. Revision 0151 validation: 379 broad checks passed with one outdated API expectation;
the revised API and follow-up checks passed (26 passed, one expected commit-visibility failure).
Revision 0152 validation: 19 core checks passed with that expected failure retained, followed by
nine passing API, immutability, isolation and migration checks. See VERIFICATION-2026-10-15.md for the full scope and limits.
Both upgrade and downgrade of 0151 refuse populated ledgers because its stamp changes the seal
document. Revision 0152 likewise refuses populated seals: their historical server completion time
cannot be reconstructed, nor may retained completion evidence be dropped. Its immutable metadata
stamp, like sealed_at, is outside the canonical line hash. No in-place populated-ledger upgrade
through these pre-release revisions is supported.



October 14 full backend CI completed on the older `165d63c` snapshot with 33 failures.
Current-main repairs and remaining failure/expected-failure evidence are tracked in
[the CI record](CI-2026-10-14.md). Targeted passes do not establish a current full release pass.
October 15 full frontend revalidation and the still-running frozen CI attempt are recorded
in [the current CI record](CI-2026-10-15.md). The repaired frontend suite passes 2,143 tests;
live review-route crawl fixtures and complete browser acceptance remain outstanding.

AI implementation status as of October 15: the internal narrative gateway composes live-job
human authorization, current settings/kill switches, serialized UTC-month budget admission,
read-only source retrieval, provider execution and audited proposal persistence. Source reads
intersect ai.use with contract.read; current grants and source evidence are rechecked around
the call. Completed-job redelivery reauthorizes access and returns the original result without
another call. The fake-provider/real-contract path is tested; no live provider call has been made.

Narrative validation checks bounded response hashes/schema, authorized node citations and
numeric membership at the currency minor unit. Invalid output keeps the deterministic
explanation; rejected text is excluded from stored proposals. These checks do not establish
semantic correctness or independent accounting acceptance. The gateway retries classified
transient failures up to three times with injected 5/10-second waits; permanent/exhausted
provider errors produce failed proposals linked to existing attempt evidence.

The read-only `/ai/model-logs` API now exposes retained call configuration, hashes, outcome,
token counters and actor metadata. Workspace-wide settings.manage can read tenant calls;
ai.use alone sees only calls with its own actor identity and kind. Visibility is applied before
counts and cursor pagination; an entity-scoped settings grant cannot read the workspace log.
List and detail responses now expose usage_known from the same evidence predicate as budget
admission. The screen labels unknown counters as Unknown and explains them in the drawer;
confirmed zero usage remains zero. Stored compatibility counters are not rewritten. This is
presentation of existing evidence, not resolution of unknown usage or admission failures.
This endpoint neither calls a provider nor depends on AI being enabled. The SF-15 call-log screen now renders calls, outcomes and a docked evidence drawer. Bookmarked
drawers reread GET /ai/model-logs/{id} under the same current visibility as the list, including
404 for another user or tenant. Its configuration-only content is escaped text.
Saved views now retain the column layout and sort under SF-15:ai-call-log; the selector can
read shared layouts and creates private layouts. View configuration never stores call records
or changes call visibility. Opening/closing evidence preserves the view and sort in the URL.
An internal export dataset builder now reuses the log's current owner/tenant predicate and
standard CSV/XLSX writers. Unknown counters remain empty/Unknown with explicit usage_known and
known-only control totals. The builder refuses system/operator and missing-ID contexts; jobs
must reconstruct the current caller before invoking it. A frozen, versioned ExportAccess record
now binds the original tenant, actor id/kind and OWN/TENANT maximum scope. Builds require that
binding; later promotion cannot widen OWN, and TENANT still requires current workspace-wide
settings.manage. A reusable read guard rejects owner/tenant/kind mismatches and permission loss.
Export guards now also require report.export (workspace-wide for TENANT). Persisted-job
requester reconstruction verifies a live attempt and active human and refreshes current grants;
its REPORT_RUN path is now connected to the internal export worker. Existing AI jobs still
narrow entity access to ai.use. API-client queued execution is not implemented.
Migration 0157 now retains an immutable ai_export_access binding on report_run, checks its
shape/tenant/creator and refuses lossy downgrade. Shared report list/addressed-read and job
list/detail predicates enforce bound ownership and current source/export grants, including
against audit readers; ordinary unbound reports keep their existing rules. The job lookup has
a partial tenant/job index. Internal report creation now captures the binding and reruns preserve
it. The REPORT_RUN handler reconstructs the human, checks before transitions/completed replay,
builds under that identity, and checks again before storing bytes. Both formats pass real queued
build tests; OWN stays OWN after promotion and permission loss prevents stored outputs. Call
exports omit accounting ledger-head metadata. Source capture is explicitly OPEN/live.
Migration 0158 registers the public CSV/XLSX definition with an empty, closed parameter schema.
It captures current authorized call evidence; reruns evaluate the live population again.
Downgrade refuses removal while export runs reference the definition.
Report API admission now uses ai.use or workspace-wide settings.manage plus report.export for
this code, including source MFA, without granting accounting-report access. An optional command
replay guard authorizes the actual retained reply after lookup; protected exports refresh session
and grants after that potentially waiting lookup. OWN replay remains OWN after promotion, while
TENANT replay refuses demotion. The call-log screen now provides CSV/XLSX export with job
progress and authorized output fetching. It hides export without the required source/export
scopes, prevents overlapping submissions, and reports permission loss instead of saving a file.
Leaving the screen suppresses a late download; source-only users need no accounting-report page.
Linked-proposal navigation and full-hash copy controls are implemented. The linked-proposal
read retains source permissions; a bookmarked number explanation is reauthorized and must bind
to the displayed calculation trace. Standard demo/J-19 and full audit-lifecycle verification
remain open; this does not implement the Explain submission trigger or other AI operations.

Migrations 0147–0150 retain append-only call logs, immutable proposal content with guarded
human-decision fields, completed-job/source bindings and immutable call intents with one
optional outcome link. Populated completion/intent evidence prevents destructive downgrade.
The gateway now commits a validated/audited call intent before provider execution and links
the outcome atomically to its log/proposal. Retained failure codes and retry decisions allow a
new worker to resume within the same three-call limit and observe remaining 5/10-second
backoff. A permanent or exhausted failure can be finalized after restart without another call.
A missing outcome refuses with AI_OUTCOME_UNKNOWN; a returned but invalidated result refuses
with AI_RECOVERY_REQUIRED. Neither case silently sends the call again or creates a zero-usage
log. Current source/permission checks and exact job/input bindings remain in force.

Unknown outcome reconciliation, unknown token usage and durable admission failures remain
open. An unobserved call now blocks new admissions for the entire tenant, across month boundaries,
until outcome evidence exists. Only the currently admitted lease can bind its newly committed,
human-owned intent for the post-call check; another job/lease cannot exempt that start. The
monthly lease still accounts for known committed usage. New attempt logs distinguish validated
response or provider-error counters (`REPORTED`), unsent admission refusals (`NOT_SENT`) and missing usage
(`UNKNOWN`) in writer-derived immutable metadata. Actual zero responses remain distinguishable
from zero compatibility counters on failures. Historical logs are not rewritten. The guard now blocks new calls for returned errors with unknown usage, including legacy errors
with no response evidence, across months and jobs. Invalid markers also refuse. Typed reported
error counters are validated, counted and allow bounded retries after fresh admission; the current
Anthropic SDK exception path supplies none, so those errors quarantine new calls until reconciliation.
Returned messages now include cache-read/cache-creation tokens in total input usage. Rejected
metadata/content retains validated totals on the error; missing/malformed/overflowing counters
stay unknown. Cache/output breakdowns are not double-counted. This uses mocked SDK coverage;
there have been no live provider calls.
Permanent/exhausted failure proposals and previously completed delivery do not make new calls
and remain recoverable. Reconciliation is still absent: there is no automatic expiry or override.
The guard does not estimate missing usage,
reserve unknown response tokens, reconcile returned provider errors without usage, or infer
historical calls that never had retained intents. The worker now registers a narrative AI_TASK
handler with validated source selectors, lazy provider construction and gateway-owned waiting.
It reports the persisted proposal identity, not human approval. Cancellation is cooperative:
before another call and during retry waits it stops without a synthetic proposal; an already
started call still retains its usage and result. Retry waits heartbeat and check cancellation
at one-second boundaries, with no database transaction or budget lease held while sleeping.
This does not interrupt a network call already in progress. Other AI operations, durable
admission-failure evidence, notifications, other submission routes and remaining proposal acceptance workflows
remain unfinished. The AI audit-lifecycle gate remains open; worker dispatch and internal
gateway tests do not satisfy the full lifecycle.

The immediate tenant disable command now requires workspace-wide settings.manage and fresh
MFA, atomically records the switch and cancels queued AI jobs, and returns the original stamp
on repeat requests. The emergency switch overrides an enabled published policy. A new AI
publication whose whole values enable AI now clears the switch under independent human
approval with workspace-wide settings.manage. Retained legacy requests also require their
original configuration approval permission. First
enablement and emergency-switch clearing withhold automatic approval; an unrelated budget edit
while AI remains enabled keeps normal routing. Publication replay cannot undo a later disable,
and publishing ai.enabled=false leaves the switch intact. There is no direct enable command.
Administrator-only AI authoring is now available at `/api/v1/ai/settings/versions`: list, create,
read, update with If-Match, queue the existing policy validation/simulation job, submit and
withdraw. These endpoints require workspace-wide settings.manage and its MFA guard, fix the
category/scope to tenant AI, and refuse other-category or other-tenant version IDs. They reuse
the registry version, audit, hashing and simulation lifecycle and expose no publish/enable
shortcut. General accounting authoring still requires config.author. Generated OpenAPI and
TypeScript definitions include the new endpoints. The /settings/ai editor now uses them.
The version list supports status filtering, version/date sorting, counts and cursor pagination.
It fixes category/scope to tenant AI before pagination and shares the individual-read scope
predicate. Administrators can rediscover drafts, submitted requests and published history without
accounting read permission. Runtime status is now available at GET /ai/settings under the same administrator guard. It reuses
the AI job settings reader and distinguishes published enablement from workspace/platform
disablement, with provider, model, token budget, text-sending and redaction values. The typed
frontend reader preserves these distinctions and propagates errors. The administrator settings page
now displays runtime availability and the platform warning, edits all eight documented settings,
resumes DRAFT/TESTED versions (including reset-to-default values), validates before submission and
links pending approval requests. Emergency disable requires confirmation and remains available while validation runs. Retries retain their
original values, row-version precondition and command keys; failed validation never submits.
A lost response after committed submission is recovered by replaying that submission's own key.
The page keeps the application's existing minimum-width guard; it is not a mobile settings editor.
Effective form values and reset defaults now come from GET /ai/settings/values, guarded by
workspace-wide settings.manage and limited to the AI catalogue. The page no longer calls general
policy-resolution or registry-catalogue reads. A custom role holding only settings.manage passes
form reads, validation-job reading, submission and independent approval; general configuration
reads remain forbidden. A real-browser submission with that custom role also passes.

New AI submissions now use AI_SETTINGS_VERSION and workspace-wide settings.manage for review,
so a different Tenant Admin can read and approve without accounting configuration privileges.
The normal lifecycle retains self-approval refusal, MFA, content hashes and emergency-switch
semantics. Retained REGISTRY_VERSION requests keep their original routing. settings.manage is
now classified as an approval permission: API clients cannot acquire it, and effective client
grants filter it out. Migration 0156 updates permission metadata and report subject filters.
The administrator-only approval regression now passes, including legacy routing coverage.
The standard demo fixture and complete J-19 journey remain outstanding. A real local Chromium
check now covers administrator settings submission through a queued validation job and confirms
AI stays disabled pending approval; it does not prove the full demo or independent accounting
sign-off. General accounting privileges remain unchanged.

Number-explanation submission now serializes admission with the tenant switch. Model changes,
including a reset to the catalogue default, and enabling contract-text sending now require an
independent administrator decision even while AI is off. Turning text sending off retains normal
routing. These changes alone do not clear an emergency switch. Provider selection remains process
configuration (EREV_AI_PROVIDER); tenant approval gating for provider changes is not implemented.

POST /ai/explanations now accepts the number-explanation form and returns an idempotent AI_TASK
job with a Location header. It checks overlapping ai.use/contract.read source access and the AI
switch before enqueueing, without calling a provider in HTTP. New jobs bind the validated trace
and use a server-selected 2048 output-token limit; the worker refuses a changed trace before a
call. Existing jobs without a trace binding retain their source fingerprint format. Anomaly
submission, full browser extraction review, existing-record acceptance and Q&A remain unfinished; a persisted
worker proposal is not a completed human workflow. Budget admission is still checked by the
worker, and durable AI-specific admission-failure evidence remains outstanding.

GET /ai/proposals now pages authorized NUMBER_EXPLANATION and CONTRACT_EXTRACTION evidence, with kind/status filters,
optional authorized totals and stable cursor pagination (created_at descending, then id descending
by default; id and created_at sorts supported). Source checks happen in SQL before paging and
counting, and apply again on every page. For extraction, only distinct referenced source-file
metadata is inspected through the existing ownership rules before SQL paging/counting; no
proposal body or document text is read during authorization. Readable IDs use one UUID-array
parameter. This preserves shared-upload and attachment permissions but still performs per-source
authorization work; large-tenant latency/load verification and optimization remain outstanding.
Unsupported kinds are excluded, including from totals.
The shared list protocol refuses invalid filters/cursors and cursors with changed filters/sorts.

GET /ai/proposals/{id} now returns retained NUMBER_EXPLANATION evidence, including content,
citations, status, actors and row-version ETag. Each read intersects current ai.use and
contract.read entity grants and requires a visible current or past member contract of the
retained calculation trace. Tenant-only trace RLS is insufficient by itself; the same member
check now protects completed-job recovery. Reads remain available with AI disabled and make
no provider call. The detail route also returns CONTRACT_EXTRACTION evidence after checking a
current human ai.use grant and original ATTACHMENT/PDF access through the file ownership rules.
It selects only binding metadata before authorization, then returns suggested fields, citations,
source/text file IDs and the common status/actor/ETag metadata. Unreadable or shredded sources
return 404; AI disable does not prevent retained reads. Other kinds still fail closed. Extraction
list integration now uses the same source ownership checks before pagination.
POST /ai/proposals/{id}/reject supports number-explanation and extraction proposals for a human
with current source access, a nonempty reason and the current If-Match ETag. Rejection locks
the proposal, advances its row version and records the reviewer and audit event in one
transaction; expired or terminal items cannot be rejected. Current extraction source access is
checked before cached response replay and again inside the command. Competing reviewers using
the same ETag cannot both succeed. Rejection preserves content/citations and makes no provider or
accounting writes. It remains available with AI off.
SCH-11 now expires overdue proposed rows daily at 03:20 UTC, in bounded tenant transactions
with row locks and SYSTEM audit events. Locked review rows wait for a later sweep; terminal
states and retained evidence are untouched. Rejection already enforces the exact expiry
boundary between sweeps. Other proposal kinds remain unfinished.
The field-review component now validates explicit ACCEPT/EDIT/REJECT decisions against every
retained path exactly once. It preserves accepted values, validates edits without coercion,
requires reasons for edits/rejections, omits rejected values and produces detached decision
records in proposal order. Unknown paths, ambiguous replacement values, invalid retained fields
and incomplete/duplicate decisions fail closed. Draft conversion requires explicit contract identity, currency, quantities,
obligation keys and structured terms; those cannot be inferred from the extraction catalogue.
Explicit draft intake now reuses ContractCreateIn, requires matching review/draft entity codes,
forbids activation and accepts one-to-one mappings from retained line paths to draft obligation
keys. Mapped product, exact amount and explicit draft currency must agree; rejected lines cannot
be mapped, and missing quantities/identity/currency are not inferred. Additional human-authored
lines remain possible.
Combined draft review now requires explicit header mappings for customer name, effective date
and payment terms. Names must match the explicitly supplied inline customer or a matching
resolved customer ID/name; no name search or fuzzy resolution occurs. The human chooses inception
or signature for an effective date, and the selected draft date must match exactly. Payment
terms also match exactly. Every retained header must be mapped: term months, termination,
variable-consideration terms and material-right review text currently refuse combined review
rather than being silently ignored or converted to accounting classifications. Rejected headers
cannot be mapped. The acceptance command freshly resolves existing customers in the caller's
tenant. Structured-term mappings remain unfinished. Correction to the earlier implementation notes: SM-11/BR-AI-05
requires AI_PROPOSAL_ACCEPTANCE for changes to existing records, not creation of a new draft.
New drafts are accepted as the human and require AI_ASSISTED activation review. Activation now
derives that flag from immutable accepted extraction-to-contract links, preventing auto-approval
regardless of amount. It includes proposal/model-log IDs, accepting human/time and a decision
hash in the activation approval basis, preserving historical hashes for contracts with no AI
provenance. The accepting human is excluded from deciding activation, including by delegation.
The draft acceptance endpoint now checks human ai.use and contract.create for the selected
entity and current source access before cached replay and again under the proposal lock. It
requires If-Match, an unexpired proposed row and at least one retained field. Normal draft
creation, source-PDF attachment, combination suggestions, rule holds, acceptance metadata and
audit commit together. It returns 201 with the contract ID and Location; it never submits for
activation or posts revenue. Retained review works with AI disabled. Existing-record acceptance
still needs its separate approval subject. Full browser review and structured-term conversion
remain unfinished. A local PostgreSQL witness now uploads the synthetic PDF through the files
API, runs real PDF text extraction and queued worker dispatch with the bundled deterministic
provider's nine-field response, reads retained text and accepts a human-reviewed draft. Customer
and product edits are explicit; accepted payment/date values and the source amount are checked
in the persisted booking, and rejected terms/lines do not enter it. It verifies unchanged original
evidence, all nine recorded field decisions, shared reader access through the attachment,
AI_ASSISTED activation provenance, one provider call and zero revenue postings. This uses the
in-process parser and does not prove Linux isolation, browser review, live-provider operation or
full extraction-to-independent-activation readiness. Extraction detail/list reads now expose the
accepted draft target, human/time and recorded decisions separately from original evidence.
A typed frontend API module now covers proposal lists/detail, retained text, submission,
rejection and acceptance, preserving server ETags and the existing command idempotency rules.
SF-20 now has a live /contracts/review/:proposalId route for retained evidence and whole-proposal
rejection. It shows original text, original versus recorded edited values, acceptance metadata
and the draft link. Source citations highlight validated Unicode code-point spans, focus the
highlight and return focus on Escape. Reads are permission-gated; expired/missing-ETag items
cannot be rejected, and rejected commands retain their reason and problem. Component/API tests
and a local browser preview cover this evidence view, not the full workflow. The preview uses
cached synthetic responses, not a live API. SF-20:new now supports nonempty PDFs up to 25 MiB,
source upload, extraction submission, job polling/cancellation and navigation to the retained
proposal. Its job URL resumes after reload, including when AI has since been disabled. Uploads
are reused across failed submission attempts; successful upload does not create a contract.
The Contracts entry uses existing AI permission/enablement checks. ai.use now permits ATTACHMENT
uploads for this pre-contract review, without granting attachment-to-record or other upload
permissions; the normal ownership, file bounds and audit rules apply. The frontend submits
file_id only, matching the implemented API; entity selection belongs to explicit draft creation.
A local Chromium probe used mocked HTTP responses for upload/job navigation, not a live provider.
Field controls now record Accept/Edit/Reject choices, require explicit low-confidence choices
and reasons for edits/rejections, and seed the ordinary draft form through explicit bindings.
Effective dates require a chosen meaning. Unsupported retained terms prevent continuation;
rejection requires a human reason. Draft creation requires normal form validation and a separate
confirmation, then calls atomic acceptance with the source proposal ETag. This path offers no
activation action. Component tests cover confirmation, retry and navigation; they do not prove
a live browser/API workflow. Returning to field review now preserves local draft inputs and
reapplies changed review choices to their matching fields/rows. Rejected source rows are removed;
human-added rows remain. Retained deleted rows are restored with unique identities and keys.
Renamed keys are rebound on continuation; draft value changes still require matching field
decisions. This recovery is in-memory, not a saved draft across reloads. Below 1440 px,
Document / Proposed fields panel tabs retain choices across pane and viewport changes;
citations switch to Document and Escape returns focus after the fields pane becomes visible.
The document page selector renders one source page at a time, and citations select their source
page before focusing the highlight. Component checks and a cached-data Chromium preview cover
these interactions; they do not establish a live browser/API acceptance workflow. DOCX extraction,
unsupported accounting-term mappings and full browser acceptance remain unfinished. Changing a bound draft field/key can cause the server to refuse acceptance; the UI
does not silently change a recorded field decision to match it.

The bundled deterministic extraction fixture now accepts a real upload identity and the
worker's full allowed-field catalogue only after reconstructing and matching the entire
known redacted-document request. It reuses retained sample values/confidences and rebinds
source citations; unrelated documents/prompts/digests are refused. This is a prerequisite
for live browser fixtures, not evidence that demo seeding or complete browser acceptance
already works. The macOS AI unit run skipped two Linux-only resource tests. Subsequent actual
worker-image verification on clean b4b8210 passed Linux PDF extraction, memory/CPU enforcement,
credential stripping and timeout reaping, and validated all nine bundled fields against a new
upload identity. All three runtime images built and passed hardening checks. API and worker
images include the synthetic AI fixture bundle. See CI-2026-10-15.md for image identities and
scope: the non-strict build and isolated probe do not establish live browser acceptance or
complete release readiness.
Broad architecture verification identified missing contract-key arguments in AI proposal
writers, unlisted expiry SYSTEM/platform callers and a stale pending AI_TASK entry. These
identified defects are now repaired: narrative rejection/expiry audit events name their source
contracts, while unaccepted extraction events explicitly name none. All 24 targeted architecture
checks and eight isolated PostgreSQL lifecycle/API checks pass. See CI-2026-10-15.md; these
repairs do not constitute a new full CI or browser acceptance pass.

The Anthropic adapter is mock-tested, uses the official SDK, disables SDK retries and telemetry,
and resolves secrets lazily. Contract-review and explain-narrative prompts have retained bytes,
digests and deterministic fixtures. Request preparation minimizes and redacts inputs with
immutable coordinate mappings; extraction validation verifies allowed paths, confidence and
source citation spans, rejecting an entire malformed proposal. Confidence below 0.75 is marked
for review. The fixed extraction catalogue now admits customer name, effective date, whole-month
term, payment/termination/variable-consideration/material-right review text, and up to 500 indexed
line suggestions containing only product code and exact decimal amount. Values are checked in
original parsed JSON before canonicalization: money numbers, impossible/non-ISO dates, coerced
terms, unknown paths and extra line keys refuse the entire proposal. These are review facts;
customer/product resolution, currency, structured contract conversion, semantic review and
full browser acceptance remain unfinished, alongside anomaly and Q&A workflows.

The worker-only document retrieval helper now checks the current initiating human, AI switches,
text consent, readable ATTACHMENT/PDF source, file size and digest before invoking an injected
isolated extractor. It audits decrypted reads as that human, heartbeats around parsing and
rechecks cancellation, grants, settings and source access afterward before preparing redacted
input with retained citation mappings. It holds no SQL transaction while parsing. This is a
preparation component. POST /ai/contract-extractions now accepts only {file_id}, checks current
human ai.use and readable, unshredded ATTACHMENT/PDF metadata, requires AI/text consent, and queues
an idempotent AI_TASK with a Location header. The server pins the source digest, fixed field
catalogue and 16000 output-token limit. Submission serializes with the emergency tenant switch;
replay rechecks source access before returning saved job data. HTTP never parses or sends text.

A separate persistence component retains original pages as encrypted AI_DOCUMENT_TEXT files
bound to the source digest and initiating job. It rebuilds requests and citation mappings from
those bytes, verifies the call intent, and atomically records model usage, validated extraction
fields and audit evidence. Invalid/uncited output and refusals produce failed proposals without
retaining rejected response text. Database tests cover encryption, cross-job text/intent
refusal, changed request fields, missing permission and rollback. Extraction review and
full browser acceptance remain unfinished.
Terminal provider-failure persistence now also rebuilds retained document evidence and verifies
the existing failure log against its request, initiating human and job intent. It links that log
without recording another attempt, preserving reported or unknown usage. Tests cover changed
failure codes, unrelated logs and rollback. The extraction gateway finalizes permanent failures
or exhaustion after three calls, without duplicating the last attempt log.
Migration 0155 adds paired source/text links to immutable call intents, so recovery can locate
the retained input before a proposal exists. Both files have evidence holds from call start;
reviewed erasure remains required and the links grant no extra read access. Intent retries and
proposal persistence must preserve these links. Populated bindings block lossy downgrade.
A worker-only recovery reader now reauthorizes the human and reconstructs exact prior requests
from intent-linked retained text without reparsing the PDF. It returns an existing proposal or
validated failure/usage/backoff metadata; an unresolved start or unclassified outcome refuses
automatic recovery. Completed evidence remains readable with AI disabled but not after access
revocation. The extraction gateway now uses that reader before each attempt, rechecks settings
and source access, holds the tenant budget lease through committed usage and limits execution
to three calls with 5/10-second backoff. Interrupted waits preserve remaining delay, retries
reuse the retained request, unknown outcomes/usage block new calls, and mid-call invalidation
records usage without a proposal. No model fallback or SDK-level retry is introduced.
AI_TASK dispatch accepts bounded extraction selectors, source hash and field paths; the worker
composition root supplies the isolated PDF parser and lazy provider factory. The public API
still needs full browser review and acceptance. Queue selectors and gateway paths
now use the fixed catalogue; arbitrary accounting fields cannot be requested.

The PDF adapter has file/page/text and parser limits, an isolated subprocess, timeout cleanup
and a sanitized environment. A four-page fixture covers the nine documented extraction fields.
Linux address-space/CPU enforcement is implemented but actual Linux success/exhaustion checks
remain unverified: two tests skip on this Mac, and Docker's daemon is unavailable. This is
process resource containment, not a filesystem/network sandbox. The registered extraction job
connects authorized reads, isolated parsing, retained text and proposal production. Local
gateway/worker database tests inject a deterministic parser and fake provider; they do not
prove the production Linux parser or a live provider works.

Proposal source and extracted-text references hold files against direct erasure, including
after expiry. The Controller-reviewed EVIDENCE_SHRED flow can lift the holds; without durable
entity bindings, review covers every tenant entity. AI_DOCUMENT_TEXT uses per-file encryption;
tests prove decryption before erasure, key destruction and refused reads afterwards. Any
experimental plaintext AI_DOCUMENT_TEXT object from an older build requires explicit migration
or regeneration; there is no plaintext fallback or automatic conversion.

File-read ownership is registered. Derived text requires ai.use and current access to a live
source attachment of a same-tenant CONTRACT_EXTRACTION proposal. Source references add no
read grant; attachment entity scope and voiding remain effective. Derived-to-derived links
refuse without recursion, and disabling calls does not disable retained evidence reads.
GET /ai/proposals/{id}/document-text now returns original numbered pages after current source
access checks and an audited encrypted-file read. It verifies plaintext size/digest and the
canonical source/job envelope, enforces page/text bounds, refuses shredded text, and works with
AI disabled. Other proposal kinds return 404. No model call or document parsing occurs during
review. Full browser extraction review and structured-term acceptance remain open.

Earlier architecture failures and subsequent fixes are preserved in the build history.
The October 15 full architecture plus file API run passed 292 checks in 226.83 seconds
(.run/ai-file-access-regression.log); 14 focused file-read checks passed separately. These
passes do not establish a full release pass. A subsequent gateway-recovery/AI/full-architecture
run passed 493 checks with two Linux-only parser-limit skips (.run/ai-recovery-final.log).
Current results are recorded in PROGRESS.md. Independent accounting sign-off and the other release gates remain open.

October 14 audit continuation: native option entry/expiry and CLOSE evidence-pack creation
now have catalogue entries and real request scenarios in the audit walk. Material-right
AUD-FACT summaries require a contract key and retain the created ids in detail. Evidence-pack
and control-execution labels are registered. 26 focused checks passed; see PROGRESS.md for
scope. The AI proposal lifecycle category and full current-main release verification remain
open; the category failure was not exempted or converted to a pass.

October 14 entered-option SSP continuation: immutable storage, native entry/read/UI,
activation content and bundle assembly now preserve an optional total SSP. Populated
snapshot recovery covers the explicit amount for open and expired options. Migration
capture/promotion still refuses option records. The shared term writer is implemented with
persistence/rollback checks and a real platform-applier witness. Exact quantity-unit
reconciliation now passes through retained evidence, with drift and equal-raw-number refusals.
A read-only promotion review now rechecks/fingerprints durable evidence and reconstructs
confirmed opening choices against captured input. It replays the retained output hash and
rebuilds contracts against current configuration inside a rollback-only savepoint, comparing
all output fields except the input identity hash. Review binds the complete pre-activation
checklist, rejects failed non-review prerequisites and exposes distinctness/collectibility
reviews as pending, never passed. Its basis includes the exact proposed judgement content and
per-book dated collectibility assessments. Creating/reviewing those judgements under approval and final
activation admission remain unfinished, as do policy publication, report validation, atomic
live creation and the approval route.
See MATERIAL-RIGHTS-IMPLEMENTATION.md for evidence and remaining boundaries.

October 7 sandbox correction: monetary verification now reads and compares the stored
`loss_provision_version` and `fx_layer_movement` results. These are reconstructed per-period
loss tests and FX history within each computation version, rather than predecessor deltas.
Duplicate FX movements remain distinct; changed amounts or rates and missing rows produce
findings. Scoped export/load and negative-control evidence is in PROGRESS.md. This resolves
the omitted-table drift guard, not the broader release limitations below.

October 7 Step 1 continuation: B1-13 is closed. Assessments affecting soft-close or reopened
posting windows require independent date review, retain the proposed figures, and compute
atomically on approval. Changed inputs invalidate review; revoked reviewers cannot decide;
rejection, withdrawal and repeated decisions cannot apply effects. The request, preview and
all resulting event evidence survive snapshot export/load. See
STEP1-DATE-APPROVAL-CONTINUATION.md and PROGRESS.md for scoped verification and its boundaries.
The broader B1-2 and independent accounting sign-off remain open.

This file states what release 1.0 of eRev Cloud does not do, does differently from what its governed documents say, or has not been measured to do. Release 1.0 is the product as it stands on main at commit `4832c645c` (the freeze of 2026-10-03 13:09) with two register indexes placed behind the freeze: index 308, the withdrawal of policy overrides (supervisor ruling R-126 (b) (1) and (c)), and index 309, the refusal on a product or an obligation template of three policy parameters that the books read for a contract alone (rows B3-13 and B3-21), which the supervisor placed under the same reason and records in ruling R-127. The file was written on 2026-10-03 on the integration branch, from `0372e7388` to `783f340ea`, under ruling R-126 (d). It has no revision table and no test pins it; when a limit is closed, its row is taken out by the change that closes it.

October 7 continuation: B5-3 and C-1 were closed on `codex/import-job-recovery` by atomic
import-job cleanup, lock-wait recovery and queued-cancellation handling. See `PROGRESS.md` for
new verification; all remaining release evidence below retains its original date.

October 7 product continuation: B1-16 is closed for contract admission and new obligations.
Mandatory disaggregation attributes are checked at booking/draft replacement, activation submission
and approval, native additions and legacy amendment application, including dated bundle components.
Incomplete catalogue drafts remain editable. Findings identify the product and missing codes;
failed application rolls back events/obligations. See PROGRESS.md for scoped verification.

October 7 close-waiver continuation: B1-10 is closed for automatic gate membership. Waivers
bind the recorded source-item identities, including reconciliation instances and missing-kind
conditions. New or replacement members lapse an approved waiver even when the count does not
grow. Pending decisions refresh the gates without needing a cockpit visit and void a changed
basis. Resolving covered members is allowed; a spent waiver never revives. Count-only legacy
waivers with live blockers need a new review. Submitted identities remain in the audit trail;
old lock certifications are unchanged. This binds membership, not every mutable field of a
member. B1-11 is also closed for completed-request sequencing: a pending approvals-gate
waiver retains its submitted request identities while completed requests drop out. The decision
checks the live population is a subset; new or replacement pending requests still require a
fresh waiver. If every request completes, the gate passes and the unneeded waiver is voided.
See PROGRESS.md for scoped verification.

October 7 reopen-evidence continuation: B1-12 is closed. An error-correction reopen requires
an independently reviewed `ESTIMATE_VS_ERROR` judgement for a contract of the same tenant/entity
and applicable book. Submission binds its content and review identity; final approval rechecks
both under locks. Missing, stale or superseded evidence cannot reopen the period. The request
keeps its submitted evidence and the completed reopen retains its citation. Legacy requests
without a citation require resubmission; historical locks are unchanged. See PROGRESS.md and
REOPEN-JUDGEMENT-CONTINUATION.md for scoped API, concurrency, migration and frontend evidence.
The accountant remains responsible for the conclusion; this does not provide accounting sign-off.

October 7 approval-availability continuation: B1-15 is closed. Pending requests show a live
warning when the active step has no independent eligible decider. Availability uses the existing
assignment rules, including delegation, subject exclusions and later-step reservations; reads do
not change routing facts. Submission and next-step activation notify active access administrators
whose own `role.manage` grants cover the request. The alert contains only its reference, with
normal notification preferences and sandbox email restrictions. Headers withholding request
content also withhold availability. Unsupported subject implementations retain their existing
named refusal. See PROGRESS.md for scoped verification; this is not full-volume performance proof.

October 7 close-task continuation: B1-9 is closed for the command flow. Signing requires the
configured owner role for the period's entity; closed periods refuse signing. An approved reopen
clears current manual-task signatures and requires fresh attestations, preserving immutable history.
Revision 0135 allows repeated close-cycle signatures and refuses lossy downgrade. It does not
rewrite existing tenant rows. The continuation index audit found that 0131's FX-layer index
placed a key behind a non-leakproof enum comparison under RLS. Revision 0136 reorders it; all
17 migration/index/doctor checks pass. This is not full-volume performance evidence.
See PROGRESS.md for actual scoped verification; no full-backend pass is asserted.

October 7 modification continuation: B1-6 is closed. Submit requires explicit boolean answers
to every retained classification proposal on every linked modification row. Approval rechecks
older pending requests before application. Classification and preview do not confirm answers;
editing the questionnaire invalidates classification/preview and voids a stale pending request.
The preparer must save answers, reclassify and preview again. See PROGRESS.md for scoped tests.

October 7 password-change continuation: B1-34 is closed. Wrong current-password checks share
the sign-in failure budget under the identity-row write lock, persist failure/security evidence,
and enforce the fifth-failure 15-minute lock. Concurrent attempts, expiry and existing password
rotation/reset races are verified; the frontend displays the 423 lockout response.

October 7 approval continuation: B1-14 is closed for the recorded draft/proposal paths. Stored
draft creators and successful content editors cannot decide a request submitted by someone else,
including through delegation. SYSTEM creation on behalf of an uploader retains that attribution.
SSP and principal/agent proposals are authored and submitted atomically and retain the existing
preparer exclusion. The per-subject evidence and dated verification are recorded in PROGRESS.md.
Other parts of C-6 remain open.

October 7 policy continuation: B3-14 is closed; C-2 is partially implemented. Approved contract-pinned rows now
reach calculation, with scope precedence, historical approval cutoffs and preserved product
pins. A real PostgreSQL approval/computation regression verifies POL-122 balance classification.
Public API creation now validates POL-122 obligation overrides and POL-047 contract financing
rates, with independent approval and real database calculation regressions. POL-163's period-scoped
contract exception, broader product readers and platform answer-key coverage
remain open. The workbench now supports draft creation, submission and status for these two keys;
optional reviewed-judgement attachment is still API-only. Historical statements
below that *no computation reads an override* describe the October 3 release, not this continuation.
The contract-period isolation foundation for POL-163 now preserves entity defaults, historical
approval cutoffs and forced IFRS15 treatment. Liability layers now retain their originating
contract and use that contract's period policy for consumption and remeasurement. A real close-pass
regression verifies the persisted FX journal and repeat-run idempotency. POL-163 public creation
remains disabled: monetary-to-historical transitions require a reviewed treatment and effective-date
model. Unreconciled carrying amounts now refuse calculation before changing the stored calculation
or ledger. Close-run policy comparisons include effective contract exceptions, with real close-job
coverage. Policy approvals now serialize with period locks, including waived pending-approval
gates and stale-decision rollback; transition treatment and public authoring remain open.
See `ACCOUNTING-REVIEW.md`
for the pending accounting decision and sign-off record. This is not a complete policy workflow.
The owner has limited current work to repository completion and explicitly excluded deployment.

The file has three classes and two tables beside them:

- **A. What stands before production use** — matters that are not the build programme's to close.
- **B. The limits of release 1.0** — by area: controls; close, locks and rates; contracts and the engine; reports; imports and the legacy migration; access and entity scope; sandboxes; operations; and the facts of the screens and their copy that the record holds.
- **C. What moved to the next release**, in the order lane ACCT would take it.
- **The fifteen standing names**: the fifteen tests of the backend suite that do not pass in release 1.0, each tied to its cause.
- **Sentences of the governed documents that say more than the product does.**

How a row reads. *Limit*: one sentence, in the product's words. *Consequence*: what follows for figures, authority or work. *Practice*: what a customer or operator does to avoid it, where the product as built offers a way; a dash where it offers none. *Source*: where the fact is recorded. A "contract group" is what the engine computes together: one contract, or the contracts of an approved combination.

- "R-124 (l)" is a clause of the supervisor's rulings log, `docs/reviews/loop/prod/RULINGS-2026-09-29.md`.
- "record 31" is an item of section 6 of the programme's record, `docs/reviews/loop/prod/RESUME-2026-09-29.md`.
- "index 294" is an item's number in the supervisor's register of the programme; the rulings log names each index it uses.
- "register" and "notes" are the supervisor's register and running notes of the programme, working files that are not in this repository. A source that names one of them says that the detail of the row rests on it.
- "measured" and "read" are the record's words: a fact measured through the product by a lane or by the supervisor, or read from the code. "Read on the tip" is this file's own reading of the code on the integration branch that day, from `0372e7388` to `783f340ea`. "Run of record" is the supervisor's whole backend suite on `5c3b5347c`, the first parent of main's commit (R-125 (n)).
- "Read on main at `b8f4b9e29`" is the supervisor's reading of the code on 2026-10-04, after the release candidate was declared, while the illustrated guide (`docs/guides/illustrated-guide.md`) was checked against the screens. Rows B4-12 and B6-8, the quick lists of row B3-12, the last row of section B.9 and the last two rows of the table of sentences rest on it, as does the practice of row B1-16 (the sentence stands in the product's drawer, not on its page); the same check corrected five sentences of the user guide that the screens had overtaken.

Every amount in this file is quoted from the record; none is a new measurement. Nothing here is an accounting conclusion: where a reading of the standard is named, it is the reading of the lane that made it, and the independent accountant's review (row A-1) stands before it. No decision named here is recorded as approved by anyone outside the programme.

Row labels (A-1, B1-1, C-1) are this file's own and are not numbers of the register.

## A. What stands before production use

These are not limits of the build. They are what a production use of release 1.0 waits for, and the programme that built the release does not close them (R-126 (a), (d), (e)).

| No. | Limit | Consequence | Practice | Source |
|---|---|---|---|---|
| A-1 | No independent revenue accountant has reviewed the accounting decisions the product rests on: decisions AD-1 to AD-40 of the review package `docs/accounting/reviews/G12-REVIEW-PACKAGE-2026-09-30.md`. | The release gate is not an accounting sign-off. Every figure the product posts rests on decisions recorded as the programme's own; none is recorded as approved. | Before production use an independent revenue accountant decides the package (gate G12). Who that is and the scope of the review are themselves open (AD-24). | R-126 (a); record 2 |
| A-2 | The accounting and control points that this programme's rulings opened are candidates only: those up to AD-72 and seventeen points without a number stand in the package and in its dated addendum, `docs/accounting/reviews/G12-REVIEW-ADDENDUM-2026-10-01.md`; AD-73 to AD-86 and six further points are named in the rulings log and the programme's record and have no packet in this release. | Each names a place where the product does one thing and the reviewer or the owner of the IT general controls may require another. None is ruled as accounting; the supervisor's rulings stay labelled as rulings. | Put them to the reviewer with the package; R-124 (k) and R-125 (k) hold the later points. | record 10; R-124 (k); R-125 (k) |
| A-3 | Answer key VC-CHK-113 does not pass: for a price concession after a modification the engine states 364.98 billed to date where the key expects 400.00, and after the concession a contract liability of 60.00 where the key expects a refund liability of 60.00. | Whether the key or the engine is right is an accounting question (AD-14, AD-15) reserved for the reviewer. The key stays red; it is one of the fifteen standing names. | Decided with row A-1. | R-46 (d); record 7; run of record |
| A-4 | Nothing is deployed, and the hosted inputs UI-1 to UI-14 are not given: the cloud projects, the region and database tier, buckets and keys, secrets, the registry and the first release tag, domains, the identity-aware proxy, OIDC and SMTP, monitoring channels, the restore-test project, the penetration test, the supported self-hosted shape, the reviewer and the subprocessors. | No hosted evidence exists: no deployment, no alert policy with a real channel, no restore test in an isolated project, no penetration test. The release candidate's evidence is local. | Supply the inputs listed in `docs/reviews/loop/prod/unknown-inputs.md` and produce the hosted evidence before the first production tenant. | record 4; R-126 (a) |
| A-5 | On the hosted road the platform bounds a request, and a response that is not streamed, at 32 MiB, while the product accepts import source files of 50 MiB and legacy databases of 500 MiB. | A larger upload or download would be refused by the platform and not by the product. The bound is read by a lane from a summary of the provider's documentation and is not verified. | Choose the road before hosting; R-124 (m) (10) records the supervisor's recommendation ("road C"). | R-124 (l), (m) (10); record 33; notes; read, not verified |
| A-6 | Under the local key provider the secret of an adapter connection cannot be resolved: that provider serves the three master keys only. | A self-hosted deployment that runs `EREV_KEY_PROVIDER=local` can run no live adapter. Release 1.0 ships none, so nothing fails today. | A guarded design is owed before a live adapter is used on a self-hosted deployment. | record 3 |
| A-7 | Performance at volume is not measured: `make perf` has not run at volume, and its harness's month 24 is not built, as the seed builds months 1 to 23. | No acceptance figure of the performance requirements is on record. On record below volume: the Home read at a median of 2.6 to 3.5 s on the demo workspace at machine load 45; about 48 minutes of processor time for the close's first period-end step at 12,500 contract groups, by arithmetic from 106 groups measured; 8.9 to 9.7 s a page for the drill of a journal line of 66,000 source lines. | Measure at the customer's own volume before production use. The known costs are in section B.8. | R-126 (b) (8); R-124 (m) (9); record 32 |
| A-8 | A workspace whose only other access approver has expired or was deprovisioned by its identity provider cannot change access until an operator restores an approver, and no operator command for that is built; who at the customer may ask for it, and how the request is verified, are not set. | Access administration of such a workspace stops until the provider acts by hand. | Keep at least three holders of `access.approve`, so that one departure leaves two. | record 11; R-126 (b) (1); read on the tip |
| A-9 | The governed documents cite the Codification by paragraph number and paraphrase it: no sentence of theirs is a verbatim quotation checked against the Codification. | A paraphrase can differ from the paragraph it cites, and the rulings and readings named in this file rest on paraphrases. | The reviewer reads the cited paragraphs in the Codification. | R-124 (k), (m) (10); record 33 |
| A-10 | Release 1.0 is installed on a new database: a database written before the release is reset, not migrated. | A workspace born on the release holds no policy override. A stored approved override of before would still be answered by `GET /api/v1/policies/resolve` as the value in force, which no computation uses; and a table that holds a ledger line written before the release's revision 0124 does not cross that revision. | Install on an empty database. No workspace is deployed today. | R-126 (c); R-125 (d) (1); index 308 |
| A-11 | A contract whose payments lie more than a year from the transfer of its goods or services is computed only on a reviewed judgement that its financing is not significant, or is excepted under 606-10-32-17: the product computes no financing adjustment (row B3-14). | Lane ACCT's reading: the pressure of that limit falls on the judgement. A record that says not significant where the component is significant gives revenue without the adjustment, with nothing shown but the record. | The reviewer reads every such judgement record. What stands in the product is the record's review by a second person. | read on the tip; index 308 |

## B. The limits of release 1.0

### B.1 Controls that the documents state and the product does not enforce

`make controls-report` (gate G7) counts 46 of the 49 controls with a passing tagged test on the integration branch at `783f340ea`, with 422 tagged tests passed; on 2026-09-30 it counted 36. Measured by the supervisor on 2026-10-03. The three controls without one are features that are not built: CTL-041, the period evidence pack (row B4-6); CTL-045, AI outputs as proposals (row C-15); CTL-048, the reconciliation of a legacy migration before its promotion (row B5-9). The count says that a test of a control passes, not that the control does all that its documents state: what a control does not do is what this section lists.

| No. | Limit | Consequence | Practice | Source |
|---|---|---|---|---|
| B1-1 | Policy overrides are offered in the workbench and API for POL-122 at obligation scope and POL-047 at contract scope. Other keys remain unavailable. | The POL-163 contract exception remains missing. Optional reviewed-judgement attachment is API-only. Supported drafts require validated values, rationale and independent approval. | Save a draft and submit it from the contract workbench; use the named existing decider for unsupported keys. | October 7 continuation; see PROGRESS.md for dated validation. |
| B1-2 | A posting into a period in soft close or into a reopened period waits for a second person only when it comes from an import or a manual adjustment; nine other kinds of command post there on their sender's word alone. | As a lane read them from the code: events an API client sends; seven event types a person records that do not wait; apply hold and release hold (9,764.38 measured in a reopened October); update memos; a judgement's submission or a distinct review on an active contract (1,873.97 measured into a soft-closed September); adapter sync and webhooks; an exception's reprocess; the close run's recompute in a reopened period; an activation that a rule auto-approves. The rule for both states is ruled and built on no branch. | Detective only: a line posted into a reopened period is marked as posted after the reopen, and the re-lock is a Controller's decision. Agree outside the product who records in a period that is in soft close or reopened. | R-124 (b) (7), (l); record 31; R-120 (a); R-123 (e) (5); notes: the list read and the two amounts measured by a lane, 1 to 2 October |
| B1-3 | The difference report of a re-lock is computed inside the re-lock's decision, so the Controller who re-locks cannot read it before deciding. | It compares end states — a hold applied and released shows nothing — and "Open diff report" leads to a report that has no builder. The re-lock is therefore not decided over its difference report. | Before the re-lock read the out-of-period register and the JE population of the period, whose column "Post-close" marks an entry posted after close; after it, the stored file of the difference report. | R-124 (b) (7); read by a lane |
| B1-4 | The approver of an attribute change is shown no impact preview. | A change of the performing entity moves revenue between two entities' books, and its approver decides without the figures. | — | R-124 (l); record 31 |
| B1-5 | Closed October 7, 2026 for estimate-version submission and approval: constraint reviews seal the specific version and its financial inputs. Reusing an earlier version’s record or editing reviewed figures is refused; edits during review make that review stale. | Historical unbound reviews remain history and cannot support a new approval. No posted estimates are rewritten. | Withdraw an old pending estimate, prepare and independently review a fresh constraint record against the actual draft, then resubmit. The drawer supports replacement after a refused record; no-change attestations retain their existing path. | R-124 (g) (3), (k) (11); CTL-049; API regression evidence in PROGRESS |
| B1-7 | Closed October 7, 2026: final estimate approval rechecks the functional amount and USD-threshold flag against current rates before applying anything. | A changed routing basis voids the request and withdraws the version; EUR 46,000 changing from USD 49,910 to USD 50,140 cannot post with the earlier single approval. | Revise and resubmit for a fresh preview and Controller step. Estimate decisions and FX publication share a transaction gate, including a publication overtaking an already-started decision. Unpublished or economically unchanged rates do not force a new request. | R-124 (l); six PostgreSQL CTL-013 cases, including both lock orders and the overtaken-clock case; dated evidence in PROGRESS |
| B1-8 | The approval of a rate version that changes a value dated in a closed period raises one warning for each entity, book and period (`FX_RATE_CHANGED_AFTER_LOCK`), which holds the lock of the posting period until the closed period is reopened or the warning is waived; the difference is not computed at the approval. | A waiver — one request and one approval — accepts a difference of a closed period that the warning does not state. Lane ACCT's reading, a control finding and not a ruling: the acceptance needs the amount and no less authority than the reopen — two approvers, at least one a Controller. | Reopen the closed period rather than waive; where the warning is waived, a Controller first works out and files the difference. | R-124 (f) (6), (k) (5); R-125 (b) (9), (k) (4) |
| B1-17 | Eleven settings are read by no code, and the workspace settings form offers three of them for approval. | An approved value of such a setting changes nothing. One of them, read on the tip: `close.unacknowledged_export_block_days` is offered on the workspace settings screen and read by no code, so nothing ages an unacknowledged export batch on the close cockpit; the lock's block on an unacknowledged batch is built. | — | record 22; R-123 (k); R-124 (l); read on the tip |
| B1-18 | A record whose identity is already stored is logged and skipped, whatever its content, and a row of a file takes its identity from its upload, sheet and row number. | The same records sent in a second file are new records, and a changed record under a stored identity is not raised: REQ-DAT-011 has "collisions go to the exception queue before commit". | Read an import's dry-run diff before submitting it, and do not send the same records in two files. | REQ-DAT-011 (CTL-001); read on the tip |
| B1-19 | A control-total mismatch notifies the configured eligible integration owner, falling back to the connection’s human creator if that member is still active and can manage/read every connection entity. Assignment is to the exception only; the connection owner is unchanged. If neither qualifies (including service-created connections without an eligible owner), the blocking exception stays unassigned for exception-queue review. Recipients are never chosen by broad role broadcast. Import commit rejects unknown/repeated source-row identities and reconciles loaded plus quarantined row counts. Updated October 7: CSV invoices/credit memos independently reconcile persisted document, signed line, positive event and tax amounts/currencies before committing, then reconcile verified file-column totals. Costs, pre-standard revenue and rated usage also reconcile their stored event amounts, currencies and source identity; an absent rated amount is distinct from zero. SSP values also reconcile stored entry prices/ratios, value basis, currency and complete bands, including derived legacy ranges at database precision. New and replacement contract imports also reconcile booking line prices, currencies, quantities, unit prices and out-of-scope amounts, with upload/source-record provenance. Estimate imports also reconcile stored scalar figures, parameters, scenarios and element settings (inheriting omitted settings for existing elements). Legacy SKU SSP imports now independently translate validated source prices/ratios and reporting currency into the same stored-entry/range checks, including verified file-column totals. Legacy contract setup also reconciles source-order amounts/quantities, complete additive booking lines and linked approved VC amounts/currencies (new-element sign/defaults, existing-element settings retained). Legacy progress also independently aggregates billing, signed pre-standard revenue and delivery cells, then reconciles stored events and signed source-invoice headers/lines, including credits and zero totals. Legacy modifications now compare signed consideration/quantity deltas, treatment, SSP references and added obligation identities. CSV progress now reconciles refunds, quantities, ratios, hours, milestone weights and obligation identity. Usage also checks quantity, period/metric and obligation; cost/pre-standard events bind obligations, with cost purpose/flags retained. CSV invoices also compare stored quantities at database precision, contract/obligation/product identity, dates, invoice links and tax classifications. Bundles now compare the complete stored replacement, quantities/split ratios, component targets, sequence and effective windows. FX versions now compare set/coverage/upload identity, all entered and derived rates, dates/periods and source targets before import commit; separate FX approval remains required. See IMPORT-RECONCILIATION-2026-10-07.md for the inspected coverage. | REQ-DAT-010 has a mismatch notify the integration's owner; registered financial CSV and legacy readers now check the scoped fields listed in the coverage inventory; broader accounting/release verification and reference-data checks remain. | Read the exception queue after a sync run; review unreconciled templates' amounts on their dry-run diff. Invoice mismatches roll back the entire batch. | REQ-DAT-010 (CTL-002); read on the tip |
| B1-20 | The exception item for an unmapped product is raised by a computation. CSV v2 imports now queue it after commit; adapter booking still does not start it. | The activation refuses a contract whose product is unmapped, at submission and at approval; the item itself appears once the contract's group is computed (row B3-7). | — | CTL-003; read on the tip |
| B1-21 | Over-billing is checked on one channel, the legacy progress import: on every other channel a billing may exceed the remaining billing plan. | REQ-REC-024 rejects an upload or an API batch whose cumulative billing would exceed the remaining billing plan of a line without variable consideration. Over-delivery is checked on every channel. Not ruled: the supervisor leans to a data-quality finding rather than a refusal, an invoice being a fact of the ledger (candidate AD-80). | Tie billings to the billing system by the period's billing-to-subledger reconciliation. | REQ-REC-024 (CTL-008); R-124 (k) (1); read on the tip |
| B1-22 | Qualitative SSP methodology changes still depend on the preparer's declaration and the reviewed study. Changed entry methods or value bases already force a second approver. October 8: numeric routing now compares effective band amounts (including percentage-of-list scaling), observable points and retained unbanded cost-plus values; zero-to-nonzero and newly added/removed observable points require review. | Changes expressed in stored methods, bases or effective values cannot bypass the second step by leaving the declaration false. A methodology change not represented in those fields still needs the preparer or reviewer to identify it. | Review the study and version diff. Exactly-threshold or compensating inputs that leave the effective SSP unchanged do not trigger the numeric threshold. Dated verification is in PROGRESS.md. | REQ-SSP-007 (CTL-010); October 8, 2026 continuation |
| B1-23 | Selected SSP bands now carry natural keys into stored obligation range IDs and calculation source references. | Formula-only and bypass prices have no selected band; merged obligations retain each contributing band in the trace and store a scalar range ID only when all contributors share one. Historical computations are not rewritten. | Implemented; verification recorded in PROGRESS.md. Include changed output metadata/trace in pending 0.4.0 release-cut replay evidence. | CTL-011; October 7, 2026 |
| B1-24 | A completeness failure that refuses a lock request or approval now retains CTL-019 evidence after the refused transaction rolls back. | The period-state reference also covers a missing journal run; failed approval/lock writes stay rolled back. Evidence includes the measured gate count/detail, observation time and period version, with its own audit. | Implemented October 8, 2026; current verification in PROGRESS.md. Ordinary cockpit reads do not create refusal evidence. | REQ-JE-005 (CTL-019) |
| B1-25 | Journal generation now validates active currency codes and the line's stamped functional currency against its entity, alongside account/dimension/FX checks. Successful runs record CTL-020 evidence in the generation transaction, linked by the calculation audit. | Failed lines refuse the whole run and produce named journal exceptions; no passing evidence survives a rollback. Empty populations record NOT_APPLICABLE. Held lines are excluded and counted explicitly. | Implemented October 8, 2026; dated verification in PROGRESS.md. | CTL-020, REQ-JE-022 |
| B1-26 | A correcting journal entry does not name the entry it reverses: the reference is written empty, and corrections arrive as delta lines. | The control's evidence, the reversal lineage on lines, does not exist; the requirement allows delta lines. | — | CTL-023; read on the tip |
| B1-27 | A billing document dated in a period that is already locked is in no billing-to-subledger reconciliation: a period's population is the documents issued in it. | A late-dated invoice is reconciled in no period. Ruled, not built. | — | R-68 (a) (CTL-024); read on the tip |
| B1-28 | On the trial balance that release 1.0 takes, a CSV upload, a direct entry in the general ledger on an account the subledger controls is not named. | The difference is an item of the reconciliation in the class of other differences; it is not flagged as high risk, as REQ-CLS-016 has it for a direct entry. | The reviewer of the subledger-to-GL reconciliation asks for the ledger's entries behind an unexplained difference. | REQ-CLS-016 (CTL-025); read on the tip |
| B1-29 | Exact role-basis freshness implemented October 8, 2026: reviewed, attached GL reconciliations are compared with the shared attachment reader on every gate/KPI/blocker evaluation, beyond chain position and document counts. | Changes in any of the three amounts, signed account membership or not-stated evidence invalidate the review. Zero roles omitted by the comparison retain zero semantics. The API mapping-change witness holds chain/counts unchanged. Volume and full-current release verification remain open. | Regenerate and review an outdated reconciliation. | CTL-016, CTL-025; [dated evidence](RECONCILIATION-ROLE-FRESHNESS-2026-10-08.md); 04 T-CLS-06 |
| B1-30 | The subledger-to-GL reconciliation is never certified automatically at zero variance: only the billing-to-subledger kind is generated with a comparison and certified under a published rule. | A subledger-to-GL reconciliation is compared when its trial balance is attached, and is prepared and reviewed by people in release 1.0. | — | REQ-CLS-017 (CTL-026); read on the tip |
| B1-31 | A run of a report again reads the first run's sources for 11 of the 37 built reports and evaluates the other 26 afresh. | REQ-RPT-002 has "Re-running with the same snapshot reproduces identical totals and hash"; for the 26 a second run can differ where the data has moved since. The count is a reader's. | For a locked period read the report as locked. | REQ-RPT-002 (CTL-029); read by a reader of the control inventory |
| B1-32 | A failed tie-out of a report refuses nothing. | A run whose tie-out failed is stored, shown and exported like any other; the tie-out's result stands on the run. | Read a run's tie-outs before using its figures. | R-78 (b) (CTL-030); read |
| B1-33 | The approver of a configuration version reads "No contracts affected" where nothing was simulated: the impact simulation has no source of contracts. | The sentence says nothing of the version's effect. Applying a version to existing contracts is itself a ruled limit of release 1.0. | The approver reads the version's difference to the version in force. | REQ-POL-006 (CTL-031); R-112 (i); read on the tip |
| B1-35 | The controls that record into the control evidence registry link none of their records to its exceptions, and nothing exports the registry. | The registry is read through its list in the API, and an exception of a control is found by that control's own list. | — | CTL-042; read on the tip |
| B1-36 | An import that an API client uploaded may commit under a published auto-approval rule, and the control's evidence then records a pass without an approver. | The import approval of such an upload is the rule's, not a person's. | Publish no auto-approval rule for import commits where a person's approval is the control relied on. | R-120 (b) (CTL-044); read on the tip |
| B1-37 | No judgement record is read for an SSP override — its command asks a justification and an approval — and for the principal-or-agent conclusion, the licence's nature, the repurchase and the series classification and the constraint of breakage a record is asked only where the conclusion departs from the product's or the template's value. | REQ-POL-008 makes a judgement record mandatory for nine conclusions; a command asks for one for three of them — the Step 1 conclusion, the distinct override and the modification treatment override — and for the constraint of an estimate version (row B1-5). | State the judgement of an SSP override in its justification and attach the analysis to the request. | REQ-POL-008 (CTL-049); read |
| B1-38 | The close run raises no finding where a variable-consideration estimate was not reassessed for the period, or where a royalty accrual is missing: `VC_REASSESSMENT_MISSING` and `ROYALTY_ACCRUAL_MISSING` have no producer. | A period locks without either check. The engine states the facts; the close step that reads them is not built. | Review the period's estimate versions and royalty statements before the lock. | R-103 (a); read on the tip |
| B1-39 | The approver of a contract combination is shown no figures: the request carries no impact preview. | A combination allocates the transaction price of its contracts anew, and its approver decides on the proposal and its judgement record alone. | — | R-112 (i) (6); read on the tip |

### B.1a Smaller findings of the control inventory's readers

Each was read by a reader of the control inventory at the line the inventory names; this file's lane read no further. The cited lines are unchanged on the tip.

| Control | Finding, as read | Source |
|---|---|---|
| CTL-002 | A batch still in flight does not hold the lock; a failed import of an API client has no owner to notify. | read by a reader |
| CTL-010 | The threshold that calls the second approver of an SSP version compares it with the prior version of the same book only. | read by a reader |
| CTL-011 | No check finds two SSP books of equal scope that overlap. | read by a reader |
| CTL-014 | A manual adjustment prepared through an API client excludes no person from deciding it. | read by a reader |
| CTL-015 | A soft close can start without a reason; an adjustment deferred past the lock is checked against its own period, not the one it posts into. | read by a reader |
| CTL-020, CTL-021 | The journal line at the legacy grain carries no dimensions; the file export checks no dimension values. | read by a reader |
| CTL-025 | The separation at sign-off is between the two signers only: whoever generated or explained a reconciliation may review it. | read by a reader |
| CTL-031 | The configuration change register carries a count of the changed fields, not the difference. | read by a reader |
| CTL-040 | The dead-letter state of a job is the state FAILED; eleven job kinds have a retry limit of 1. | read by a reader |

### B.2 Close, locks and rates

| No. | Limit | Consequence | Practice | Source |
|---|---|---|---|---|
| B2-1 | Five places state a locked month from the contract versions and not from the lock's datasets: the Home's contract liability panel, the cost rollforward's closing tie, balance aging, the book bridge and the adoption bridge. | After a later event that reaches a locked month these five can differ from what the lock froze. The lock's datasets are the record of a locked month; the contract balance rollforward, the contract balances and the revenue from the opening liability read them. | For a locked month read the report as locked. | R-126 (b) (7); R-124 (h) (4), (m) (8) |
| B2-2 | A computation that commits before the approval of a corrected rate, or whose cutoff lies before the corrected version's publication, is stored on the earlier rate, its contract group clean and unmarked; the group's next computation posts the difference. | Until that next computation the ledger holds the earlier rate's amount, and the lock's gates do not count the group. | Approve a corrected rate while no import and no computation runs. | R-126 (b) (9); R-125 (f) (2) (i) (b), (c); index 294; measured |
| B2-3 | Where the approval of a rate version commits between a computation's read and its posting, the computation is stored as failed and nothing is posted; the next computation posts. | A blocking item is raised, where a computation behind its group is otherwise answered 409 and sent again. The form of this failure is held as it is. | Reprocess the blocking item; it clears. | R-125 (f) (2) (i) (a); measured |
| B2-4 | The approval of a rate version holds the rows of the contract groups it marks until it commits; past the request's lock timeout the approver is answered 409 `lock-conflict` and nothing of the decision is stored. | A close run or a computation of a group the approval reaches waits for those rows and, past the 10 s lock timeout, ends as failed or is answered 409. | Send the approval again; work a close run before a rate approval or after it has committed. | R-125 (f) (2) (iii); index 277; measured |
| B2-5 | Where the only unposted amounts of an earlier period cancel between two subjects of one contract group in one account role, the period is neither refused nor held by the close gate. | Two offsetting amounts of an earlier period can stay unposted through its lock. Recorded as the limit of the gate's net; not built, not measured. | — | R-125 (g) (2), (l) |
| B2-6 | A period whose contract group's latest computation was refused locks when the engine's finding and the gate that every contract is computed are both waived; the group's netting reclass of that period end is then never posted. | Measured: January locked with a reclass of 1,000.00 unposted. The locked period's contract balances stay as its last run presented them; the next period's reclass states that period's own position. Put to the reviewer as an accepted limitation, a disclosure or a defect. | Do not waive both: resolve the refused computation before the lock. | R-122 (e); R-124 (k) (4); record 20; measured |
| B2-7 | A deferred computation for a contract group that a combination then empties is stored as failed, with a blocking item that names no contract and no entity. | No close gate counts the item, and only a waiver ends it. | Waive the item. | R-125 (l) |
| B2-8 | Updated October 8: a later seal anywhere through a GL reconciliation's period end now makes it out of date, matching the ledger history read by its comparison. Older timestamp-based rows use the same period range. | An earlier-period posting requires a fresh GL reconciliation even if it writes no reversal into the reconciled period. Billing reconciliation remains period-scoped. | Implemented; scoped PostgreSQL evidence in PROGRESS.md. Exact role-balance comparison and volume verification remain open under B1-29. | CTL-025; prior measured limit R-124 (f) (4), index 299 |
| B2-9 | The lock decision produces its datasets inside the deciding request. | The approver's request lasts as long as the datasets take; how long that is at volume is not measured (row A-7). | — | R-116 (h); record 12 |
| B2-10 | The History of a journal run names the submission of its approval request and not the decision that answered it: a rejection, a void or a withdrawal of the request writes nothing with the run as its object. | The same holds for the lock request and the reopen request of a period. The decision, its decider and its comment stand on the request. | Read the decision on the request, under Approvals. | R-124 (l) (JRN-HISTORY-DECISIONS-1); `docs/design/SCREENS_B.md` §3.2; notes; read by a lane |
| B2-11 | A posted manual adjustment cannot be voided or reversed: the request is refused 409 with "A posted manual adjustment cannot be voided. Correct it with a further adjustment." | The PRD's path of an adjustment from posted to voided is not built. | Prepare a further adjustment that carries the correction; both stay in the register, each with its preparer and approver. | R-112 (b) (1); `docs/guides/user-guide.md`, "Manual adjustments"; read on the tip |
| B2-12 | A manual journal or an account reclassification is refused for a contract that is not in its entity's functional currency. | A correcting journal or reclassification cannot be booked on a foreign-currency contract; a release, a deferral and a schedule override are not limited. An adjustment applies in the book it names, and no other book is adjusted. Stated limits of the first release, put to the reviewer. | — | R-112 (b) (3); read on the tip |
| B2-13 | One batch of a journal run that the ledger has partly posted cannot be cancelled. | Wrong content in such a run is corrected in the subledger and posted by hand with its correction; a failed batch of it leaves by a retry or by the hand-over. | Hand the failed batch over: download its file, post it by hand and record the ledger's document number. | R-112 (c) |
| B2-14 | A close run is started for one entity: no route starts the close of several entities at once, and the view of several entities starts one run for each. | The close of a group of entities is as many runs as it has entities. | — | R-113 (h) |
| B2-15 | A line that the close run posts at a period end has no stored calculation trace and no replay evidence. | The period end's postings cannot be explained from a stored trace, or replayed, as a contract's computation can. Recorded for the reviewer and for the owner of the IT general controls. | — | R-79 (d) (CLOSE-PASS-TRACE-1) |
| B2-16 | The subledger-to-GL reconciliation states a contract balance role only for contracts in the entity's functional currency or with a stored functional balance at the period: otherwise the role's row reads "Not stated". | The product does not translate a balance. Such a row carries no subledger amount, names the contracts and the reason, is a variance that the preparer explains and the reviewer signs, and is never certified automatically. | Explain a "Not stated" row from the contracts it names. | R-74 (a) |

### B.3 Contracts and the engine

| No. | Limit | Consequence | Practice | Source |
|---|---|---|---|---|
| B3-1 | For a usage obligation with a fixed fee, the current part of an earlier period, as a later version restates it, also holds the usage fees realised since. | On the item's candidate answer key the version of 30 September 2026 states the current part of 31 December 2025 as 163,750.00, where the version of that date states 100,000.00; no read of the product serves an earlier period's current part from a later version. The key waits for the reviewer outside the release selection (AD-61). | — | R-125 (k) (1); R-124 (g) (13); index 87; `docs/accounting/ENGINE_SPEC_B.md` S10-R-24 |
| B3-2 | Four points are left open with the scheduling of a usage obligation's fixed fee, as the record names them: a rate line under the right-to-invoice method that carries an allocation; stage 06 at a modification of a usage obligation with a fee; the loyalty-points exception; and 108 refusals below zero at look-backs on nine answer keys, the same without the item. | None is measured as a wrong figure; each is held. | — | R-125 (l); index 87 |
| B3-3 | Under `billing.posting` `ENGINE` a credit memo on a foreign-currency contract quarantines the contract. | The contract is computed no further until the quarantine is resolved. Whether a workspace may publish that value in release 1.0 was an open question; it stands as a limit. | Do not publish `billing.posting` `ENGINE` in a workspace that holds foreign-currency contracts. | record 24 (i); measured |
| B3-4 | October 15: manual create/edit forms now let the preparer state acceptance clauses and side letters as Yes, No or Not stated, and preserve saved answers on draft replacement. CSV v2 also preserves stated terms through approved booking and draft replacement, and rejects contradictory repeated cells. Imports and integrations that omit the terms still leave them unknown. | Missing terms still trigger TERMS_NOT_STATED. Stating terms does not bypass the existing source, flag, threshold or human-review requirements for activation. | State confirmed terms explicitly; use Not stated when unconfirmed. Integrations may supply acceptance_clause and side_letter on booking. | Contract-form request tests, activation flag and CSV v2 PostgreSQL regressions, and browser edit verification; historical R-124 (g) (6), record 24 (ii), index 261 |
| B3-5 | The thresholds of an activation are amounts in US dollars, the one threshold currency. | A known dollar amount is judged by its value; a missing functional rate sets `RATE_NOT_PUBLISHED`, which by itself takes the Controller's step. A workspace without dollar rates sends every activation in another currency to the Controller. | Publish US dollar rates for the workspace's currencies. | R-124 (g) (6), (m) (10) |
| B3-6 | A regroup is taken for two draft contracts and refused otherwise: the regroup after posting is withdrawn from release 1.0. | Measured before the withdrawal: the road moved 95,868.49 where about 60,000 remained, left the target untouched and booked a third contract with the obligation's original service dates. | Regroup while both contracts are drafts. | record 18 (i); candidate AD-83; measured |
| B3-7 | Updated October 7: CSV import commits now queue one durable CONTRACT_COMPUTE child per affected group, dispatched after commit. A minute-by-minute worker sweep now queues dirty booked groups from other paths, preserving the dirty trigger and deduplicating live jobs and dirty generations. Locked groups and enqueue failures wait for another tick; a terminal job for an unchanged generation requires job retry or exception remediation. | Figures update when the worker completes; failed computations leave the committed imported facts intact. The late-billing register now reads stored computation findings for zero-posting events (B4-7). | Monitor computation jobs and resolve calculation exceptions; periodic recovery does not bypass the engine's refusal or period-lock rules. | IPL-11; PROGRESS.md; record 18 (iv); R-63 (b) |
| B3-8 | A contract group whose performing entity keeps a book that its contracting entity does not is refused by the engine: its booking is quarantined and the contract is computed in no book. | Such a contract posts nothing. Not ruled; a refusal by name at the door is proposed. | Give both entities the same set of books before booking. | R-124 (k), last sentences; candidate AD-54 |
| B3-9 | Several readers outside a contract's computation take a period-scoped policy value once, at the instant they run: the reports' elections and the nonpublic reliefs, the exemptions and time bands of the RPO, the consumption order of the opening contract liability, and the posting mode and summarisation of a journal run. | A report of an earlier period, run after a new policy version was published, states that period under the value in force when it runs. Stated as a limit, to be measured before it is ruled. | Publish such a policy version after the periods it should not touch are locked; a locked period's report is read as locked. | R-124 (k) (2); R-122 (i); candidate AD-85 |
| B3-10 | At a modification the allocation follows the SSP version the preparer named for an obligation, while the price test of an added line reads the version in force at the modification date. | One modification can allocate an added line from one SSP and test its price against another; the screens say that the test's figures are those of the version the test read. Left to the reviewer. | — | R-124 (k) (6) |
| B3-11 | October 15: new SSP override requests retain the contracting entity, SSP book entity, all-entity scope and mismatch indicator in their hashed review preview. The approval table labels these facts explicitly. Existing stored requests keep their original preview. | Cross-entity pricing remains possible when the requester can read the source book. The accounting conditions for using another entity's observable prices and whether a mismatch needs another approver remain unresolved; this change adds visibility, not a new policy decision. | State whose book supplies the price and why the entity's own book gives none. Withdraw and resubmit an older request to include the new entity facts. | SSP reach/approval PostgreSQL and rendered approval-table regressions; R-124 (k) (9) |
| B3-12 | October 15: current open-exception counts and both values of the Has exceptions filter now read related OPEN/IN_PROGRESS queue items under tenant/entity scope. Direct contract, obligation, current group and combination-suggestion attribution are covered; repeated occurrences count once. Modified-in-period and Modified this period now select contracts with APPLIED modifications effective in their contracting fiscal calendar; the quick list uses the selected as_of date or entity-local today. Recently viewed now persists up to 50 successful contract opens per caller, orders by latest open and rechecks current contract access. | Modification membership reflects current status, not reconstructed historical status; recent history is operational and disposable on downgrade. | Use the exception queue for details and the Modifications tab for modification history. | Contract exception-count integration and scope regressions; historical R-76 (d), R-124 (l), index 205 |
| B3-13 | For seven policy parameters the framework's default applies to every contract in release 1.0 — `sfc.discount_rate_basis`, `cpc.incentive_asset_release_basis`, `royalty.unreported_sales`, `royalty.minimum_guarantee`, `concession.allocation_basis`, `usage.tier_minimum_method` and `upfront_fee.recognition_period`. | Six of them allow the level of a contract, which is withdrawn (row B1-1): "The framework's default applies to every contract in this release." Two list a product or its obligation template as a level — `usage.tier_minimum_method` beside the contract's, `upfront_fee.recognition_period` alone — and the engine reads them with the contract alone: on a product, on a change of a product's policy values and on a template version they take the default only — 422 `validation-failed`, field `policy_values.<key>`, rule `POLICY_PRODUCT_LEVEL_NOT_READ`, with a sentence that names the parameter: "This release reads usage.tier_minimum_method from no product or template. The framework's default applies to every contract: leave it out, or state the default." Until that refusal such a value was stored, published with the template's version and not used; the industry template FRANCHISE-RIGHT loses the `CONTRACT_TERM` it stated, and no figure moves. For every contract POL-049 stays `EXPECTED_PURCHASES`, POL-056 `ACCRUE_ESTIMATE`, POL-057 `FIXED_ON_LICENCE_PATTERN`, POL-243 `INCEPTION_BASIS`, POL-240 `DERIVED` and POL-029 `EXPECTED_BENEFIT_PERIOD`; their other values — `COMMITTED_PURCHASES`, `AS_REPORTED`, `ROYALTY_WITH_FLOOR_TRUE_UP`, `TARGETED_WHEN_32_40_ATTESTED`, `ESTIMATE_MEASUREMENT_PERIOD_TP`, `CONTRACT_TERM` — can be chosen for no contract. POL-047 keeps a basis and a compounding and has no rate (row B3-14). Measured on the engine for POL-240, on a key of the corpus: stated on the template, every figure stays as before; stated at the level of the contract, as the control, ten figures move — the transaction price from 363,750.00 to 300,000.00, revenue to date from 138,750.00 to 75,000.00, the contract liability from 125,000.00 to 188,750.00. | — | R-126 (b) (4), (c); index 308; index 309 (PRD ERR-103); census read by a lane; POL-240 measured on the engine, not through the product; the registry read on the tip |

| B3-15 | When a judgement record that holds a contract is discarded, the contract's hold is not released with it. | The contract stays on its recognition hold until a person releases it. | Release the hold on the contract's header with "Release hold" after the record is discarded. | R-124 (g) (2), (9); index 174 |
| B3-16 | A contract that fails criterion (a), (b) or (c) of 606-10-25-1 cannot be booked: the accounting of an arrangement that is not yet a contract is modelled for criteria (d) and (e) and for 606-10-25-4 only. | Consideration received before such a contract exists is outside the subledger. Candidate AD-59 for the reviewer. | Account for it outside the product until the criteria are met. | R-113 (f) |
| B3-17 | For an active contract the criteria-met path serves a book that was put out as not probable only: a book put out for another reason, such as no commercial substance, is refused by name. | Such a book does not re-enter through the product in release 1.0. Candidate AD-56 for the reviewer. | — | R-102 (a) |
| B3-18 | A book adopted after a contract's activation computes the contract on the strength of its approved activation: no Step 1 re-assessment is asked for the new book. | Candidate AD-46 for the reviewer. | — | R-61 (f) |
| B3-19 | A contract whose inception date is corrected keeps the SSP version it was priced with until an SSP override names another. | An obligation's SSP is read back from the version recorded when it was priced; a later publication does not price an existing contract anew. | Request an SSP override where the corrected date calls for another version. | R-116 (d) |
| B3-20 | A product's code is frozen once a contract line, an SSP entry or a mapping rule names it; a source order line and an integration alias do not freeze it, and a booking in flight during a rename is not guarded. | A rename can leave a source record or an alias that names the old code. | Rename a product only while nothing refers to it and no import or sync runs. | R-112 (i) (4); R-120 (d) |
| B3-21 | `pob.shipping_as_fulfilment` takes no value on a product or an obligation template, though the registry lists that level: 422 `validation-failed`, field `policy_values.<key>`, rule `POLICY_PRODUCT_LEVEL_NOT_READ`, "This release reads pob.shipping_as_fulfilment from no product or template. The entity's or the workspace's value applies where the framework does not fix it: set it by a policy version." | The engine reads the parameter with the contract alone, so a product's or a template's value never reached the books; until the refusal it was stored, published with the template's version and not used. Whether shipping and handling after the transfer of control are a fulfilment cost is one answer for an entity, not one for each product: under ASC 606 the entity's or the workspace's policy version and, where none holds it, the default `TRUE`; under IFRS 15 the framework fixes `FALSE` for every contract, whatever a version holds. The registry still lists the level for this parameter and the two of row B3-13, and the registry screen prints it. | Under ASC 606 set the value by a policy version at entity or workspace level; under IFRS 15 there is nothing to set. | index 309 (PRD ERR-103); census read by a lane; the registry read on the tip |
| B3-22 | Four policy parameters decide nothing at any level — `step1.portfolio_approach` (POL-015), `material_right.ssp_method` (POL-026), `costs.commensurate_ratio` (POL-142) and `scope.lessor_combination_expedient` (POL-231): a value stated for one, on a product or a template or by a policy version at workspace or entity level, is stored and published, and changes no figure. | Each is named in a stage's list of keys and in the policy memo, and no rule reads it: a stated value enters the key by which the engine recognises that stage's output, and moves nothing else. No refusal is built for them. What decides in the books, read on the tip: every contract carries its own estimates, and the product builds no estimate version for a portfolio; the SSP method of a material right is the one stated in the option's own terms; a cost asset is amortised over the contract term unless POL-141 reads the contract's approved renewal expectation, and no test compares a renewal commission with the initial one; a line follows its own scope flag — a lease line takes its share of the allocation and is routed out of the revenue obligations — and nothing combines a nonlease component with a lease. The migration's prerequisites write POL-026 `ENTERED_AMOUNT` and POL-231 `NOT_ELECTED` on every product they create, and the legacy SKU import does so under the legacy-parity preset; the check of a product's policy values admits both. | State the method in the option's terms, the scope on the contract's line and the renewal expectation as an approved estimate; rely on no value of these four. | index 309; census read by a lane; read on the tip |
| B3-23 | `GET /api/v1/policies/resolve` consults the override levels, the registry's versions and the framework's default, and no value of a product or of an obligation template. | For the fourteen parameters that the books read with the obligation — POL-030, 051, 053, 055, 071, 072, 090, 091, 095, 122, 140, 141, 143 and 241 — it answers the workspace's or the entity's value, or the default, where the books use the product's or the template's. No screen states the read for an obligation: its uses in the web are at workspace or entity level. | For such a parameter read the product and its obligation template, not the resolve read. | index 309; read by a lane and on the tip, not measured |
| B3-24 | Partially verified October 14: POL-029 expected-benefit-period recognition is now exercised through the full engine in ASC606 and IFRS15. | Eight new cases cover a 24-month renewal estimate, absence of an estimate, a later estimate that must not reprice inception, and an ordinary discount voucher. They assert obligation dates, unchanged option SSP and every period’s posted revenue. All 41 stage-03 suite tests pass. Native draft entry now supports immutable terms with permission, stream preconditions, pending-review guards and independent activation review. Governed corrections, replacement/race acceptance and the full method matrix remain unfinished. The workbench now exposes initial native entry, stored-term reads and expiry, with component/API checks; complete browser-to-API lifecycle acceptance remains open. T-CON-14 persistence and database guards (revision 0145), bundle translation and dated dedicated/embedded reads are implemented. Stored-terms adapter, entered-amount and discount-times-likelihood API tests reach real computation and activation. Dedicated expiry is implemented with lifecycle and date checks; manual exercise, reversal and broader closure acceptance remain unfinished. The generic route still refuses these events. Populated stored-backup restore now passes four ASC606 cases (entered amount and approved discount-times-likelihood, each open and expired), preserving terms and recomputed revenue. This is not full lifecycle or restore-release acceptance. Converted migration options are also refused. Answer-key coverage remains missing. | Implement the persisted option lifecycle described in MATERIAL-RIGHTS-IMPLEMENTATION.md, then verify it through product commands and obtain independent accounting review; this is engineering regression evidence only. | backend/tests/engine/s03_pob_builder/test_s03_benefit_period.py; .run/benefit-period-s03-final.log |

### B.4 Reports

| No. | Limit | Consequence | Practice | Source |
|---|---|---|---|---|
| B4-1 | Repaired October 20: new revenue-waterfall calculations exclude contracts entering after the performing entity as-of period end. | Original entry dates/version identities are retained; legacy bindings and already-frozen datasets retain their original population. | New calculations use the dated population; independent accounting acceptance remains open. | Waterfall entry checkpoint; API, scope, currency and regrouping checks. |
| B4-2 | Partially repaired October 8: dated realized allocation and fixed schedule components keep a later usage fee out of earlier RPO, including first-computation batching. API RPO and waterfall consume the same projected amounts and explain their component nodes. Separately traced usage no longer makes a batched fixed amendment ambiguous. | The PostgreSQL January/March case, journal tie-out and explanation links pass. October 14 API tests also cover royalty guarantee netting, delayed licence delivery and downward statement correction; migration 0144 admits the engine-supported point-in-time royalty licence template. Multi-cause fixed-allocation decomposition, adjustments/holds/Step-1 projections, zero-net omitted schedule lines, legacy upgrade handling and combined lifecycle/exemption/calendar/royalty verification remain open. Mixed legacy/detailed evidence is refused, not treated as zero. | Finish those cases and engine release cut/replays. See RPO-REALISED-FEES-2026-10-08.md for baselines, repairs and evidence. | R-126 (b) (13); R-125 (k) (2); October 8 engine and PostgreSQL regressions |
| B4-3 | RPO exemption calculations are implemented, including retained royalty and targeted variable-consideration evidence. | Original allocations and dated evidence govern partial exclusions; ambiguous multi-cause allocation remains a limitation, not a guessed exclusion. | See the dated RPO checkpoints and rpo_quotas.py; independent accounting acceptance remains open. | October 20 code inspection |
| B4-4 | Role-by-role rollforward-to-GL comparison is implemented using retained period reconciliation evidence. | Offsetting role discrepancies still fail. Missing comparable sources or unsupported currency/scope answer not applicable. New report details link to the retained reconciliation. This does not add a close-lock prerequisite. | rollforward_gl.py and targeted GL comparison/viewer tests. | October 20 code inspection |
| B4-5 | A report run by period key over entities of more than one fiscal calendar, and the waterfall and the disaggregation over such entities, are refused: 422 `CALENDARS_DIFFER`; the dashboard draws its panels for one entity, or for a scope of one calendar and one functional currency. | In the demo workspace one entity keeps an April year, so "all entities" by period key is refused there. | Run such reports for one entity, or for the entities of one calendar. | R-123 (g) (1), (4); record 24 (v) |
| B4-6 | October 20 registry census: all 59 catalogue definitions have execution paths: 55 table builders and four composed reports. | No current definition is missing registration. Registration does not certify accounting accuracy, output formats or every evidence-pack workflow. | catalogue.DEFINITIONS and framework.REGISTERED_REPORTS; retain the scenario limitations in dated checkpoints. | October 20 code inspection |
| B4-7 | Updated October 7: computed late events with stored LATE_EVENT findings now appear with zero posted effects and their explicit event amount. Findings are scoped by book, entity, origin/posting period and known_at; events already represented by ledger attribution are not added again. Event amount is null for multi-event sets, triggers or events without an explicit Money amount. | The platform fallback records findings for the primary book only (new findings pin that book; legacy findings use the primary-book fallback). A secondary book gets no row without its own stored finding. The difference a late billing makes to balance classification at an earlier reporting date is not restated. | — | R-123 (g) (2); R-124 (k) (7); record 24 (vi) |
| B4-8 | Report viewer grid filters are implemented. | Display filters operate on report rows; they do not recompute the accounting run. | ReportFilters.tsx and filterRows. | October 20 code inspection |
| B4-9 | A look-back of the RPO has one residual case that the record states as a limit and does not describe further: 124,910.14 where the ledger gives 118,430.14 at 31 January. | A contract enters the RPO at its activation, and a look-back includes what remained of an obligation at the date: candidates AD-81 and AD-82 for the reviewer. | — | R-122 (j), (n); measured, as recorded |
| B4-10 | At a look-back the functional net position of a contract's balance is served for its latest measured period only. | A read as of an earlier date answers no functional net position: the stored balance keeps none for each period. | — | R-106 (c) |
| B4-11 | A report run with an explicit `known_at` — the historical basis — cuts subledger lines by the time the application recorded them, not by the time they were committed: a line whose posting commits after that time, from a request that began before it, is not excluded. | A historical read can state a line that was not yet committed at its stamp, where a posting was in flight across the stamp; contract versions are cut on the server's clock and are not affected. The window lasts from the instant the posting request or job took its clock to its commit. It was accepted as documented when the basis was built; the remedy, a server-stamped column for the line predicate, is not built. A strict expected failure pins it (see behind the table of the fifteen names). | For a locked period read the report as locked: its datasets are frozen at the lock. | candidate 113 of `docs/reviews/loop/prod/PLAN-SUMMARY.md`; `backend/tests/domain/reports/test_historical_line_cutoff_db.py`; as that test records it, not measured again |
| B4-12 | Functional and reporting currency processing is implemented for the core reporting paths; the former blanket refusal is obsolete. | Conversion depends on original rate/layer evidence and supported report scope. Mixed TIME/EVENT attribution and unverified cross-calendar/performing-side combinations remain open; unsupported evidence is refused. | See the dated multi-currency and source-attribution checkpoints; no claim of universal currency coverage. | October 20 code inspection |

### B.5 Imports and the legacy migration

| No. | Limit | Consequence | Practice | Source |
|---|---|---|---|---|
| B5-1 | A usage report or royalty statement whose usage period ends after its date is refused where it is sent: 422 `validation-failed`, rule `USAGE_PERIOD_NOT_ENDED`, "The usage period … ends after the report's date, …. A usage report states usage that has occurred: end the period on or before …." | An integration that sends month-to-date usage with the whole month as the period is refused. Without the rule a lock froze an RPO short by the report's fee (measured before the rule: 21,739.73 where 26,739.73). | End the usage period on or before the report's date; the CSV template `usage` states the same finding for a row when the file is validated. | R-126 (b) (10); R-125 (g) (4), (m) (2); index 306; measured |
| B5-2 | A usage report dated in a later accounting period than the one its usage period ends in puts the fee's revenue into the later period, and nothing warns of it. | Revenue of usage that occurred in one period is recognised in the next. Lane ACCT's reading: the date to give a report is the last day of its usage period. | Give a usage report the last day of its usage period as its date (user guide, "Contracts"). | R-126 (b) (13); R-125 (k) (3) |
| B5-4 | Under the legacy-parity preset a legacy Contract Modification upload on a combined contract group quarantines the group: release 1.0 has no combination under the legacy preset. | The group is computed no further until the quarantine is resolved. | Do not combine contracts in a workspace that still takes legacy Contract Modification uploads. | R-126 (b) (5); R-124 (l); record 29; index 292 |
| B5-5 | The journal tie-outs of onboarded history are not built: a period whose journals another ledger holds fails two journal identities at its lock, and the workspace is shown nothing of it. | Measured in the onboarded test workspace: two identities fail in 20 of 21 locks. Lane ACCT's reading, held with the migration's scope: the identity net of what an opening baseline holds, tied once at the cutover, never a waiver. | Tie the opening balances to the former ledger outside the product at the cutover. | R-126 (b) (5); R-124 (k) (10), (l); record 29; measured |
| B5-6 | The migration's capture of a legacy database ends in an error 500 for a stated price with more than four decimal places. | Such a database cannot be captured in release 1.0. The shape of the repair is accepted and not built: accept what loses no digit, refuse by name what would. | — | R-126 (b) (5); R-124 (l); notes; measured |
| B5-7 | A modification that arrives by the legacy import stores no modification record: it is outside the modification register and has no classification questionnaire and no stored preview of its own. | The register that evidences control CTL-007 does not list it. The approval of such an import is raised to the modification's own approval. | Keep the import's approval record as the evidence of such a modification. | record 14 (CTL-007); read |
| B5-8 | The four obligation templates of the legacy-parity preset are not seeded. | A workspace on the preset authors them under their exact codes before its first legacy import, or the import refuses its SKUs. | Author and publish the four templates under their exact codes before the first legacy import. | record 18 (v) |
| B5-9 | A migration in replay mode is refused — "Replay imports (D-31 mode b) are not available yet; this migration cannot be imported." — and the promotion of a migration is not built. | Mode (a), opening balances with a cutover, is the migration of release 1.0. Control CTL-048, the reconciliation that gates a promotion, has nothing to gate. | Migrate by opening balances. | R-126 (b) (5); record 14 (CTL-048); read on the tip |

### B.6 Access and entity scope

| No. | Limit | Consequence | Practice | Source |
|---|---|---|---|---|
| B6-1 | Thirteen kinds of approval subject answer for the whole workspace and are decided by an approver who holds the permission for one entity: obligation templates, a product's principal-or-agent conclusion, rule sets, an account mapping without entities, FX rate sets, SSP books of all entities, master-data imports and six more. | Two people of one entity can put in force configuration that every entity uses. Policy versions at tenant and book scope are closed: their commands ask the permission for all entities. | Grant the approval permissions of these subjects only to people who are to decide for the whole workspace. | R-124 (e) (3); record 22, 30 (a); measured for policy versions |
| B6-2 | An API token that holds a write permission without the matching read permission submits nothing that names an entity. | A preparer is asked the subject's read permission for every entity the subject names, so such a client's submissions are refused. | Grant an integration the read permission with the write permission. | R-125 (e) (3); index 301 |
| B6-3 | Sixteen files of the web application gate a command by a bare permission, not by the permission's scope. | A member can be offered a command that the API then answers 404, as for an id that names nothing. | — | R-125 (e) (3); read |
| B6-4 | An access review needs two approvers who each hold the permission for all entities. | A workspace in which fewer than two approvers hold all entities cannot decide an access review. | Keep two holders of the access review's approval for all entities. | record 24 (iii) |
| B6-5 | Updated October 8: invitation creation rechecks the existing identity under a row lock after locking a reused membership, before ending its prior lifecycle or writing invitation effects. Disabled/erased identities, changed email addresses and operator identities are refused. | An erasure committed after the first lookup cannot revive the removed membership or queue a new invitation to its former address. The new-membership branch also refuses a disabled existing identity. | Implemented; dated PostgreSQL interleaving and access-scope evidence in PROGRESS.md. Explicitly inviting the former address after erasure may still create a separate new identity, as before. | REQ-SEC-007; prior limit R-124 (l), record 31, index 293 |
| B6-6 | The pool file and the result file of an SSP calculator run are read with `ssp.read` for all entities, which is stricter than the run's own reach. | A member of one entity cannot download the files of a run she may read; she reads the run's observations through the run itself. Nothing is shown to a reader who should not see it. | — | R-124 (l) (SSP-RUN-FILES-SCOPE-1); notes; read by a lane |
| B6-7 | A file's id is that of its stored row and is ordered by time: a member who uploads bytes the workspace already holds learns that they were stored before and roughly when, never by whom. | Accepted as a stated property of the file store. | — | R-118 (j) |
| B6-8 | On the screen only a holder of `user.manage` creates an approval delegation: "New delegation" offers its delegates from the member directory, and the read of delegates that every approver may open (`GET /approval-delegations/delegates`) is not built. | Among the default roles only the Tenant Admin holds `user.manage`. A Revenue Reviewer or a Controller sees the tab "Delegations" with "New delegation" unavailable: "Choosing a delegate needs the member directory, which your roles do not include." The command itself asks no such permission. | An approver without `user.manage` creates the delegation through the API, `POST /api/v1/approval-delegations`, with the delegate's membership id. | R-112 (g) (API-GAPS G-2 (h)); `docs/design/SCREENS.md` §15.7; read on main at `b8f4b9e29` |

### B.7 Sandboxes

| No. | Limit | Consequence | Practice | Source |
|---|---|---|---|---|
| B7-1 | An empty sandbox is staffed by one person, who can make anyone a Controller there. | The separation of duties of a sandbox made empty starts from one administrator's word. A sandbox can never export journals through an adapter and cannot write to a production workspace. | Do not take an empty sandbox's approvals as evidence of a control. | record 24 (iii) |
| B7-2 | A file that a sandbox stored itself can be shredded by nobody after the sandbox is reset. | The file stays with the archived sandbox. | — | R-124 (l); record 31 (SBX-RESET-OWN-FILES-1); notes |
| B7-3 | The administrator of a workspace learns of an empty sandbox derived from it by one audit event and can neither list it, open it nor end it. | A derived empty sandbox is outside its source's sandbox list. | The source workspace's audit log holds the one event. | R-124 (l); record 31 (SBX-DERIVED-SANDBOXES-1); notes |
| B7-4 | A sandbox copy still reads a file whose shred is decided and not yet completed. | Between the decision and the completion of a shred, a copy taken then can read the file. Stated, not closed. | Take a copy after pending shreds have completed. | R-124 (i) (3) |
| B7-5 | October 14: refused workspace-type changes retain tenant.update / DENIED. Source provenance from reset is required by SBX-02, which records sandbox creation in both tenants. | SNAPSHOT and EMPTY reset regressions now compare full source tenant-scoped rows outside documented provenance tables; both pass. The populated case includes contracts and ledger lines. The earlier no-audit defect is repaired; source provenance alone is not a defect. | Full CTL-043 and release acceptance remain separate requirements. | 1ab522c denial repair; October 14 reset source-content regressions; SBX-02 |
| B7-6 | After a sandbox copy has failed its name cannot be used again: a second copy under that name is refused 422 `SANDBOX_NAME_TAKEN`, and the archived sandbox the failed copy left has no member, so no list shows it. | The name is lost to the workspace. | Give the next copy another name. | R-124 (l) (SBX-FAILED-COPY-NAME-1); notes; the refusal measured by a lane, the list read |
| B7-7 | A hosted deployment offers no sandbox copies: under the hosted key provider a sandbox copy fails closed. | A sandbox needs an audit key of its own, which the worker's identity may not create on the hosted shape. On the compose stack the copy needs nothing else. | — | R-108 (b) (4); `docs/guides/runbook.md`, "Sandbox copies on a hosted deployment" |
| B7-8 | A sandbox copy does not reproduce its source's locked periods: where the sandbox's own close refuses a transition or a lock that the source took, the period stays at the last state it can reach and the copy raises the warning `SANDBOX_REPLAY_BLOCKED` — "… could not be re-closed or re-locked in the sandbox copy because …; the period stays …. The sandbox is usable for inspection, but it is not point-in-time equivalent to production until the period is closed the same way." | The copy succeeds, and the copied contracts are recomputed on the sandbox's open periods. The replay of a source's whole lock chain does not pass: journal runs, acknowledged batches and reconciliations are regenerated in a sandbox and not copied, and when a lane measured it on 2026-09-29 the first lock of the replay was refused by four close gates. A strict expected failure pins the finished path (see behind the table of the fifteen names). | Read a locked period's figures in the source workspace. | R-10; `docs/05-ARCHITECTURE.md` SBX-04; PRD IMP-116; `backend/tests/domain/platform/test_sandbox_replay.py`; measured by a lane on 2026-09-29, pinned since |

### B.8 Operations

| No. | Limit | Consequence | Practice | Source |
|---|---|---|---|---|
| B8-1 | A statement that names more than 65,535 rows one value each is refused by the database driver, and the product answers 503 each time; five lists name contract groups that way. | At the stated scale of 10,000 contracts and 50,000 obligations a list of contracts or obligations stays under the bound and a list of lines or events does not. Not measured on the close path: the instrument is `make perf` at volume (row A-7). | — | R-125 (f) (2) (ii), (l); R-124 (l) (BIND-LIMIT-CENSUS-1); notes; read |
| B8-2 | The two page reads of the subledger plan all 181 monthly partitions and read every matching line before the page's limit. | Measured: 2.2 to 5.7 s a request on tables that were not analysed, 98 and 73 ms once analysed, at 26,010 lines. | Keep the partitioned tables analysed (runbook RB-12). | R-124 (l); record 32; index 278; notes; measured |
| B8-3 | A close run rebuilds every contract group's bundle three times and passes groups that have not begun. | Measured: 132 of 144 seconds of a close run over the demo workspace. By arithmetic from 106 groups measured, the first period-end step takes about 48 minutes of processor time at 12,500 groups, during which every command computed for a group leaves it to a second run. | Run the close when the period's work is quiet; a second run takes up what the first left. | R-124 (l); record 18 (vi), 32; measured |
| B8-4 | A partition window cannot be extended over a month that has a row in the default partition, and a contract that ends in 2033 or later writes schedule lines there today. | The runbook's procedure RB-12 is then refused. The design of the move is accepted and held. | Extend the partition window before the first contract that ends beyond it is booked. | R-124 (i) (5) |
| B8-5 | A reconciliation generation or a sync run is stopped when its adapter retries past ten minutes without a heartbeat, and the attempt then keeps nothing; no alert is raised when the job sweeper passes over a job whose work is still open. | What such an attempt had not committed is not kept. A hosted alert policy on the log line `job.sweep_passed_over` is proposed, not built. | Watch failed jobs (runbook RB-07). | R-124 (d) (1) |
| B8-6 | A read of the audit log by contract or by chain sequence plans every monthly partition. | Such a read is slower than a read by date, which ends at its `to` or one day after the request. | Give an audit read its dates. | R-124 (d) (5); index 241 |
| B8-7 | Record search is a scan, bounded by a minimum term of two characters, a limit for each kind and the request's statement timeout. | Search time grows with the workspace's records; the key table that would serve it by index is not built. | — | R-116 (f); record 12 (SEARCH-KEYS-1) |
| B8-8 | Of the six documented webhook kinds only the two of a journal batch are emitted: `run.completed`, `import.committed`, `period.locked` and `exception.raised` are delivered by no code, although an endpoint can be registered for them. | A subscriber to one of the four receives nothing. | Poll the API for runs, imports, locks and exceptions. | R-75 (c); read on the tip |
| B8-9 | A system gate that is added after a first deployment needs a seeding step of its own: a workspace seeded before the gate existed enforces it and does not list it on its checklist. | The lock is refused by the gate's name while the checklist shows no such row. | Seed the gate's row with the release that adds it (runbook). | record 12 |
| B8-10 | No command verifies a replay or prepares a release: the handler of the `REPLAY_VERIFY` job and the `UPGRADE_VALIDATE` report are not built. | The product cannot recompute a stored computation from its pinned inputs and compare the result. | The runbook's entries RB-09 and RB-16 use the answer-key and parity gates of the release in their place. | record 18 (iii); `docs/guides/runbook.md` RB-09; read on the tip |
| B8-11 | A request body above the reverse proxy's limit is answered by the proxy's own bare 413, where the API answers a body above its limit 422 with a problem document. | A client reads two different answers for one fault, with the proxy and without it; the screens show their own sentence for the 413. The repair's shape is accepted and held. | — | R-124 (l) (NGINX-413-PROBLEM-1); `docs/04-DATA_MODEL.md` API-C-17; notes; read by a lane |
| B8-12 | The notification of a new blocker of a period in soft close (`CLOSE_BLOCKER_RAISED`, PRD NTF-08) is sent by no code, and the notification settings give every member a switch for it. | A member switches on and off a notice that never comes. | Read the blockers on the close cockpit. | R-124 (l) (NTF-CLOSE-BLOCKER-1); notes; read by a lane and on the tip |
| B8-13 | The rate limits of sign-in, of password reset and of an API client are counted in each API process. | A deployment with several API instances approximates each limit for every instance. | Set the limits with the number of instances in mind. | R-118 (j) (RATE-LIMIT-PER-PROCESS-1); read on the tip |
| B8-14 | A date picked as the effective date of a configuration version is sent as noon UTC of that date. | For an entity whose zone lies beyond UTC+11 the version reads as in force on the next local day, and a version dated today is refused once noon UTC has passed. The second is read, not measured. | Date a configuration version from the next day on. | R-59 (CFG-EFFECTIVE-DATE-1); R-120 (d) |
| B8-15 | `make tf-validate` fails in a checkout whose path is long: the Makefile gives every target a temporary directory under the gate's execution context, and Terraform's provider plugins cannot open their socket when that directory's path is longer than 86 characters. | The failure reads "Failed to load plugin schemas … the plugin failed to negotiate the initial go-plugin protocol handshake"; nothing of the Terraform configuration is at fault. Measured in a verification worktree whose path has 32 characters: the gate failed twice on the release candidate, when its process number had five digits, and passed when it had four — once on the candidate and once on `783f340ea` before it; and with temporary directories of 86, 87 and 88 characters `terraform validate` passed three times of three, failed three of three and failed three of three. In a checkout whose path has at most 31 characters the gate does not meet the bound. | Run the release gates from a checkout with a short path. | measured by the supervisor on `f8e46e542`, 2026-10-03 |

### B.9 Facts of the screens and their copy, and held names, as recorded

The record holds each of these by its name; this file gives no sentence of what the product does beyond the record's own words, quoted or shortened here, and a dash where the record gives none. None is a figure of the ledger, and none is a control of section B.1. They stand as recorded: by name and by source. The last row alone is not the record's: it was read on main at `b8f4b9e29`, as the head of this file says.

| Name | As recorded | Source |
|---|---|---|
| Index 199 | The workspace settings screen, items 2 and 3; "SF-15's form". Held; it stays out of the release. | R-124 (e) (3), (i) (4), (l); register |
| Index 250 | The contract workbench, the modification wizard and the modification's page ask command permissions of the whole session. | R-124 (l); register |
| Index 251, KIT-FIELD-MESSAGE-EDIT-1 | 34 forms, 115 fields. | R-124 (l); notes |
| Index 254 | SCREENS §4.9.8, beside "Open step 1". | R-124 (l); register |
| Index 255, KIT-LIVE-SEARCH-SWEEP-1 | 29 places in 16 route files make a link or a write from a render's search. | R-124 (l); notes |
| Index 256, PILL-ALL-ENTITIES-1 | The pill under `entities=all`. | R-124 (l); notes |
| Index 262, CTR-EXTID-RESERVED-1 | The reserved form of a contract's external id, derived from the makers' constants. | R-124 (l); notes |
| Index 267 (i) and (ii) | The Step 1 gate's reason on the Step 1 drawer; the second banner of a voided judgement record. | R-124 (l); notes |
| Index 269, POLICY-VERSION-PAGE-SMALL-1 | The withdraw dialog's sentence, the focus after Submit, the date field's text, the Tested step's sentence, a doubled full stop. | R-124 (l); notes |
| Index 270, SEARCH-OBLIGATION-CONTRACT-1 | `contract_id` on a search result of an obligation or an invoice. | R-124 (l); notes |
| Index 271, PERM-SENTENCE-NAMES-CODE-1 | A sentence that names a permission says its phrase and its code from one function. | R-124 (l); notes |
| Index 252, RPS-19 head 2 | The second head of the two dashboards. | R-124 (l); R-122 (m); register |
| "Retry export" in the header | The header of a failed journal run does not offer "Retry export"; a failed batch is retried on its row. | R-124 (l) |
| The "Handed over" caption | A journal run that was handed over shows no "Handed over" caption, though the run records when it was handed over. | R-124 (l); notes |
| "Outside your access" | An empty link stands where "Outside your access" belongs. | R-124 (l); notes |
| The rest of SCREENS_B rev 1.86 | — | R-124 (l) |
| A press undone | A press undone by a late answer's write to the address. | R-124 (l) |
| Indexes 186, 187 and 189 | OWNER-URL-READERS-1; JOB-COMPUTE-RETRY-1 with JOB-RETRY-TABLE-1; DOCTOR-ZONES-1. | R-124 (l); register |
| HOME-NO-ENTITY-1 | Before a workspace has a legal entity, and while no period of its entities is open, Home shows three error banners with "Retry" — key figures, close status, revenue by period — where an empty state belongs: the dashboard's read is refused ("No entity is in your scope."; "Choose a period. No period of these entities is open."). | R-124 (l); notes; read by a lane and on the tip |
| The web facts of indexes 234, 265, 291, 301 and 77 | Screens that offer a command the API refuses, or say nothing of a waiting approval. | R-124 (l) |
| The spent waiver's sentence | The sentence on a row that is waived a second time. | R-124 (l) |
| "Reset MFA" | Offered on an invited member's page. | R-124 (l) |
| The void of an attribute change | The refusal names two remedies — "Record a further attribute change, or request an SSP override." — whose commands the obligation pane does not render. | notes; read on the tip |
| The template editor's policy values | The panel still offers every parameter that lists the level of a product, the three of rows B3-13 and B3-21 among them; a refused value is shown in the form's banner, under "Check the highlighted fields", and no row is marked. The product's own screen has no editor of policy values: it shows them in a table, and their creation, their change and the proposal are roads of the API. | index 309; read by a lane in the code, not in a browser |
| A failed chunked step | The copy "Nothing was committed for that step", and the copy of the failed dry run's banner (SCR-ST-12). | R-124 (l) |
| The screen crawl's SF-16 | Red once in fifteen runs and green alone on the same commit; its reading — a background refetch of the member's own record that fails twice swaps the screen for its banner — is not proved. | R-124 (l), (n); R-125 (l) |
| The cockpit of a submitted period | Until its read of the period's requests has come, the cockpit says that the period has not been submitted and blocks "Lock period". | R-125 (h) (3) |
| The Messages column | The import rows grid cuts a long finding; it stands whole in the cell's title, the row's drawer and the error report. | R-125 (h) (2) |
| A revoked session | The sign-in page has no sentence for a revoked session. | R-124 (d) (3), (m) (10) |
| "Last login" of a removed member | The user access listing's "Last login" of a removed member. | R-124 (m) (10); record 33 |
| The Transaction and Functional switch | The contract workbench has no switch between transaction and functional currency. | R-116 (j); record 12 |
| Screens the user guide names as not built or not routed | Manual adjustments (API only); the help screen of the desktop map; the evidence-pack and scenario tabs of Reports; the migrations list and the new-migration screens. | `docs/guides/user-guide.md`; read on the tip |
| The RPO at a locked period end; a document voided after the lock of its period | Held with the five places of row B2-1. | R-124 (m) (8) |
| Operations without a single permission | 72 of the 422 API operations have no single declared permission on the union of a member's roles; a tenant-level template job runs under that union. | R-125 (e) (3) |
| The caveats of the rate approval's mark | The property's sample is thin; no three-session deadlock witness; no witness of an approver scoped to one entity; the statement is not measured at volume; what the approval's wait costs is read; the gate counts by contracting entity; the finding of a rate changed after a run holds the lock of the first postable period after the corrected one. | R-125 (l); index 277 |
| The Service Account role | Whether the role is meant to hold `config.read` is not decided. | R-124 (e) (6) (viii), (m) (5) |
| An unavailable primary button | A primary (filled) button that is unavailable keeps its fill and its white label and looks like an available one: it does nothing when pressed and gives its reason in its tooltip only. So "New delegation" for an approver without the member directory and "New estimate version" while a version is open. The label of an unavailable secondary button is greyed. | read on main at `b8f4b9e29` (`frontend/src/components/ui/Button.tsx`); the captures `sf-12-delegations` and `sf-03-estimate` of `docs/screenshots/` |

## C. What moved to the next release

Out of release 1.0 by R-126 (b) (1): the legacy migration beyond what is built, forecast, AI assistance, the rest of the demo world, of the platform answer keys and of the performance phase, and the registers and report builders that are not built. The order below is lane ACCT's judgement: first what bears on a figure or a control of a workspace in use, then what bears on its operation, then the modules that were never part of the built product. Where R-126 names an item as the first of its kind, the row says so.

The counts by phase come from the supervisor's scan of the build specification, run on the tip for this file. It counts, for each item, the named acceptance tests that exist; it does not run them. "Full" is an item all of whose named tests exist.

| No. | What moves | Where release 1.0 stands | Size, where the record gives one | Source |
|---|---|---|---|---|
| C-2 | Policy overrides, built: an approved override reaches the computation. With it the road of POL-122 for three answer keys (POS-CHK-012, DLT-CHK-020-CHK-022-GT07, POS-CHK-117), the exception of REQ-FX-002 by a contract-level override (POL-163), and the road to a discount rate for a significant financing component (row B3-14). Beside it, for a policy value of a product or a template: a reader that passes the obligation lifts the refusal for its parameter, by name (rows B3-13 and B3-21). | Partially implemented October 7: POL-122 and POL-047 API/workbench authoring and approved contract-pinned calculation are verified. POL-163, broader product readers, optional judgement attachment in the drawer and platform answer-key coverage remain open. | About 20 working hours and two gate cycles, by a lane's reading. | R-126 (b) (4), (c); R-124 (m) (3); record 28; index 309 |
| C-3 | Implemented October 20: dated waterfall entry population (B4-1). | New calculations use retained contract-chain entry dates; earlier frozen outputs remain unchanged. | Final candidate and independent accounting acceptance remain open. | Waterfall entry checkpoint and migration 0231. |
| C-4 | Implemented October 8: USAGE_REPORTED maps to variable consideration; dated realized-fee movement also covers the first-computation usage case. | Scoped engine and API regressions pass; this cause-map item is no longer unbuilt. The broader B4-2 limitations above remain. | See RPO-REALISED-FEES-2026-10-08.md. | R-126 (b) (13); R-125 (k) (2); October 8 regressions |
| C-5 | The second person for a posting into a period in soft close or reopened (row B1-2), with a difference report that the Controller reads before the re-lock (B1-3) and the attribute change's preview (B1-4). | Ruled, built on no branch. | — | R-124 (b) (7), (k) (8); R-120 (a); R-123 (e) (5) |
| C-6 | The held control whose shape is accepted: the notice of a request without a decider (B1-15). | Authorship exclusion (former B1-14), modification questionnaire confirmation (former B1-6), close-task sign-offs (former B1-9), and estimate constraint bindings (former B1-5) closed October 7; remaining listed controls are open. | — | R-124 (k) (11), (l); R-120 (b) |
| C-7 | The last item of the rate family (index 294; row B2-2): at the lock the gates count a contract group whose latest computation pinned a rate version that no longer answers. | Not built. | Two lanes and at least one gate cycle. | R-126 (b) (9); R-124 (g) (13); record 37 |
| C-8 | The five places that state a locked month from the versions (row B2-1). | Not built. | About two days without balance aging, by a lane's estimate. | R-126 (b) (7); R-124 (m) (8) |
| C-9 | The rest of the entity model: the thirteen workspace-wide subject kinds (row B6-1) and who authors the security, platform and AI settings. | Closed for policy versions; open for the rest. | One line a subject in the approvals kernel, and the author commands asked for all entities, as the supervisor recommends. | R-124 (e) (3), (m) (5); record 30 (a) |
| C-10 | Performance: `make perf` at volume with the harness's month 24; the close run's rebuilds (B8-3); the subledger page reads (B8-2); the census of long lists (B8-1); the key table of record search (B8-7). | Not measured at volume (row A-7). Phase PRF: 6 items, 4 full, 2 partial. | — | R-126 (b) (8); R-124 (l), (m) (9) |
| C-11 | The former missing-builder backlog is superseded: all 59 current definitions have registered execution paths. | Remaining work concerns scenario coverage, accounting acceptance and the explicit limitations in dated checkpoints, rather than 17 absent generic builders. | B4-6; October 20 catalogue/registry census. | October 20 code inspection |
| C-12 | Platform properties and platform answer keys: the suite's run of the platform keys on the database platform, where alone a platform key can pass (PRP-1 to PRP-3). | The suite takes the five standing platform keys on the in-memory platform. On the database platform two of them pass, one compares clean and is failed by the finding of the overrides it declares, one is not run and one has four mismatches (the fifteen names, 1 to 5). Phase PRP: 8 items, 3 full, 1 partial, 3 none, 1 without named tests. | — | R-124 (m) (1); record 26; measured by a lane |
| C-13 | The legacy migration beyond what is built: replay mode and promotion (B5-9), the parallel-run comparison, the tie-outs of onboarded history (B5-5), a legacy modification on a combined group (B5-4), the exact-text rule on the command side (B5-6), the seeding of the parity templates (B5-8). | Mode (a), opening balances with a cutover, is built. Phase LMG: 11 items, none full, 7 partial, 4 none. | — | R-126 (b) (5); record 29 |
| C-14 | Scenarios, forecasts and deal preview. | The scenario and forecast commands are not in the API. Phase FCS: 8 items, none full, 3 partial, 5 none. | — | R-126 (b) (1); record 1 |
| C-15 | AI assistance under human control, with the AI proposal lifecycle. | Off, and no AI route in the API. Phase AIX: 12 items, none full, 4 partial, 8 none. One standing name waits for it. | — | R-126 (b) (1); R-50 (f); record 33 |
| C-16 | The rest of the demo world, the onboarding surfaces and the serial journeys. | Phase DMO: 34 items, none full, 4 partial, 8 none, 22 without named tests. | — | R-126 (b) (1); record 1 |
| C-17 | The facts of the screens and their copy, and the held names (section B.9). | As recorded. | — | R-124 (l); R-125 (l) |

October 7 answer-key continuation: the runner now creates, submits and independently approves
supported POL-122/POL-047 declarations. The real PostgreSQL POS012 regression passes its full
key verdict with both declared overrides persisted and approved; its expected numeric figures
are unchanged. Unsupported policies still fail explicitly. C-12 remains open: the default
suite still uses memory, GT07's nondistinct mapping is missing, and POS117 needs fresh database
verification and the balance-aging builder. The October 3 measurements below remain historical.

October 7 migration continuation: historical names 13–15 are closed. The full-source test
fixtures now include February 2023 for the post-cutover contracts; all seven PostgreSQL capture
tests and three related reconciliation/report tests pass with their original expected amounts.
The broader C-13 migration backlog remains open. A fresh database POS117 run also resolves its
four historical numeric mismatches: 103 steps applied, zero refused, contract and subledger
blocks clean; its balance-aging report is still unavailable. The canonical full answer-key gate
already selects PostgreSQL via `AK_SCOPE=full`; ordinary pytest defaults to memory.

October 7 volume continuation: historical standing failure 8 is closed. Generator version 15
keeps each delivery's exact two-decimal share instead of independently rounding every batch to
a whole number. The corrected 1/1000 PostgreSQL seed passes with its original assertions;
46 pure volume/performance tests also pass, including delivery bounds and exact completed totals
across the full manifest. This does not establish full-scale database performance; C-10 remains open.

October 7 FX layer continuation: revision 0131 persists immutable T-CON-18 movement rows for
new computations, including contract ownership and source/rate/trace lineage, under tenant/entity
RLS. Existing versions are not backfilled. This closes the storage prerequisite only: balance aging
still requires its projection and historical reads. The subsequent close-monitor continuation
checks individual current-version layers through the close date, in both currencies, rather than
aggregate balances. Pre-0131 versions still have no movement coverage. C-11 and the remaining CTR-14 tables are not complete. Demo/volume generator
versions 11/16 identify the changed stored state; no full-volume seed or deployment is claimed.

October 7 aging continuation: the unregistered draft now reads liability aging from the selected
versions' persisted movements and reconciles each contract/entity/role/currency independently.
Asset/unbilled presentation still reads the interim subledger source; RPS-12 and POS117 remain open.

October 7 balance-aging completion: RPT-36 is now registered. It reads liability movements and
engine trace presentation attributions, with version-bound historical and rerun reads. The database
POS117 key and CHK-010 report acceptance pass; historical standing names 5, 7 and 10 are closed.
There are now 18 unavailable report definitions; balance aging is removed from the current B4-6/C-11
backlog. The rows below retain their October 3 evidence. Old versions without the new aging payload
refuse and are not backfilled; foreign-currency functional aging remains unsupported. Other report
builders, full-backend verification and accounting sign-off remain open.

October 7 loss-test storage continuation: revision 0133 stores period loss tests and all contributing
EAC references. The register remains unregistered. K03 exposes a separate engine discrepancy after
its change order: loss-test consideration/margin remain 1,200,000/350,000 instead of the unchanged
acceptance's 1,350,000/500,000. Storage preserves engine output; it does not close this calculation
gap or standing name 12. The stale unconstrained-price view and report projection remain open.

October 7 dated loss-consideration correction: the book fold now refreshes the unconstrained
view at boundary dates and period ends, with owner-specific approved consideration before the
collection cap. The PostgreSQL K03 regression meets the original September 1,350,000/500,000
expectations and preserves August consideration 1,200,000. This closes the calculation discrepancy
above; the register projection/registration and standing name 12 remain open. Existing stored
versions are not backfilled. Demo/volume generator versions are 14/19.

October 7 loss-register availability: RPT-31 is registered over bound period loss tests and EAC
lineage. K03's original acceptance (standing name 12), same-source reruns after later changes,
period filtering and all four exports pass. There are now 17 unavailable definitions. Missing
stored tests are refused against trace coverage; no historical backfill. Provision-cell Explain,
foreign-currency functional/reporting views and explicit locked-source reads remain open for
RPT-31. Other C-11 work, full-backend verification and accounting sign-off remain open.

October 7 loss-register Explain completion: the provision cell now opens its immutable period
loss test's trace through a bound contributor. Explain and Verify enforce tenant/entity scope;
later calculations do not replace the source of an existing report's drill. Functional/reporting
currency conversion and explicit locked-source reads remain outstanding for RPT-31.

October 8 evidence-pack continuation: the deterministic archive/manifest builder and verifier are
implemented and have 49 passing pure integrity tests. The manifest uses the separately stored
T-RPT-04 hash; it does not hash itself. RPS-16 source collection, routes, jobs, audited download,
automatic lock/re-lock generation and all complete-pack acceptance tests remain open. The
EVIDENCE_PACK handler is still pending, CTL-041 is not claimed and report availability is unchanged.

October 8 evidence-pack request contract: the four kind-specific input schemas now enforce
required/unused selectors, sample size and unique nonblank IDs, and ordered change dates.
102 schema tests and the 49 archive tests pass together. Routes, permission/source resolution
and the complete generation/download workflow remain open; these unit results do not close
RPS-16 or CTL-041.

October 8 evidence-pack selector continuation: source identities now resolve under tenant RLS
and intersected report/audit permission scopes; incomplete samples, hidden locks, mismatched
lock selectors and nonfreezing records are refused. Nine PostgreSQL selection cases pass with
the 151 schema/archive units (160 total). This is not a collector or an available pack endpoint:
payload authorization, persisted bindings, jobs, complete as-of content, files, audited download
and automatic close/re-lock generation remain outstanding. CTL-041 remains open.

October 8 frozen close-pack collector: certification, snapshot identities and twelve frozen CSV
datasets now use verified lock sources and guarded spreadsheet exports, retaining source and
served hashes separately. The real freeze producer/encrypted store and adversarial-source cases
pass in the 168-test scoped run. This portion still lacks the other required CLOSE contents,
job/API/download integration and automatic generation; the other pack kinds and CTL-041 remain
open. No report availability or production-readiness claim follows from these checks.

October 8 stored re-lock evidence: the collector now verifies the reopen history, both complete
frozen closes, and the saved comparison's metadata and full contents before returning its original
bytes and source IDs. The 182-test scoped run includes an approval-driven re-lock consumer witness.
The separate `variance_between_closes` report, remaining pack contents, job/API/download workflow
and automatic generation still remain open; this does not complete RPS-16 or CTL-041.

October 8 reconciliation collector: CLOSE packs can collect their lock-bound signing statements,
verified sign-offs or CTL-026 auto-certification evidence, and the actual population index.
Historical bytes stay stable after a reopen/new generation. Parent and referenced-contract
permissions are enforced without altering signed content. 210 scoped tests and two extended
API-signature/database cases pass. A subsequent 78-test GL/billing reconciliation and collector
run passed in 134.88 seconds, including real rule publication, auto-certification/CTL-026,
frozen-source production and deterministic collection. That witness seeds the lock approval
and supplies explicit reader permissions; the complete approval/pack HTTP/download witness
remains outstanding. Full pack/waiver completeness and the generation/download workflow remain
open; no RPS-16, CTL-041 or readiness claim is made.

October 8 saved certification evidence: a separate collector verifies the canonical saved gate
population and collects the selected lock's actual approval and checklist-waiver decisions,
with subject/entity/time/hash checks. The 85-test scoped run and two extended database witnesses
cover actual approvals, preserved waiver counts, older-lock selection after re-lock and refusal
of missing/mismatched/late approvals. Setup still seeds journal/reconciliation signals; this does
not prove a full operational close. The journal batch register, full reconciliation completeness,
remaining contents and assembly/job/API/download integration are outstanding. Full assembly must
invoke this collector; RPS-16 and CTL-041 are not complete.

October 8 historical journal register: a collector now ties batches and run totals to the frozen
JE population, checks transaction/functional balancing and counts, and carries saved journal gate
results and source hashes. Historical state uses the existing report reader; later runs are
excluded. The 105-test scoped run includes a nonempty database snapshot witness with seeded
journals/certification plus pure mismatch refusals and existing report/history regressions.
Full operational calculation/close acceptance and pack assembly remain open; assembly must also
verify approval evidence. Supporting registers/access/audit, other kinds, jobs/routes/downloads
and automatic generation still prevent completion of RPS-16/CTL-041.

October 8 audit digest collection: the collector binds an explicitly chosen successful
verification and its original digest to the lock's audit head, validates the stored file and
canonical metadata, and re-verifies the complete recorded HMAC prefix. It rejects a shorter
intact prefix and wrong anchor; later verifications do not replace the chosen source. The
71-test scoped run includes actual audit verification/files over seeded close references and
wrong metadata, purpose, coverage and permission cases. No verification or retained cloud copy
is created by collection. Pack orchestration must persist its chosen verification ID; full
assembly, remaining reports/kinds, jobs/routes/downloads and automatic generation remain open.

October 8 supporting report outputs: the five existing SSP/configuration/late-entry/access/SoD
builders now have an evidence reader for saved CSVs, IPE manifests and explicit source identities.
It enforces original report/export permissions, bound scope/selectors/cutoff and file/manifest
integrity. Five API/worker witnesses passed; a broader run had 75 passes and three test-expectation
failures (403 versus 404 for removed permission with retained scope). After correcting those,
38 affected tests passed, including byte equality with ordinary report downloads. These tests
bind to generated report selectors; they do not prove the close-pack orchestration selects the
required period-end access instant or register range. Choosing and persisting those sources,
full assembly and remaining pack workflows remain outstanding; RPS-16/CTL-041 are still open.

October 8 close supporting-source plan: the five requests now derive their entity, fiscal date
range/period, UTC period-end access instant and known-at cutoff from the selected lock. The
ordinary report framework queues each source; normalized bindings are returned for atomic pack
persistence. An 82-test scoped run includes actual queue/worker/collection over a seeded close,
calendar/cutoff boundaries and permission/historical-period refusals. UTC period-end follows the
existing register-day convention. Pack-state persistence, retry reuse and automatic close/job/API
integration remain unimplemented. Historical mutable facts that existing report builders cannot
reconstruct remain refused rather than replaced with current data; full operational close and
pack acceptance, RPS-16 and CTL-041 are not complete.

October 8 reconciliation population evidence: a reader now resolves the lock-time requirement,
retains its registry source and checks required kinds against only the lock-bound certified
population. Missing kinds need exact approved missing/unreviewed member evidence and remain
explicitly listed as waived omissions. Duplicate or unexplained sources refuse. Waiver submission
audit events now preserve the complete hashed subject; saved approval evidence checks that hash,
scope/count/members and audit-prefix coverage. Older events lacking the subject cannot supply this
proof and are not reconstructed from mutable checklist rows. Existing lock records are unchanged.
The broad scoped run passed 149 tests. An added policy-history witness initially failed twice due
to a fixture timestamp before the database freeze cutoff; after fixing that chronology, 69 affected
tests passed, including byte-identical historical output after a later policy change. These tests
use real waiver/lock approvals with seeded journal/reconciliation gate setup. Complete assembly
must invoke both population and statement/signature readers; durable jobs/API/downloads, other
pack kinds, the separate variance report and operational close acceptance remain open. RPS-16,
CTL-041 and production readiness are not claimed.

October 8 durable CLOSE sources: migration 0142 adds immutable `evidence_pack.source_binding`.
Preparation verifies an explicit digest and queues five report sources; the retained versioned
contract fixes request/scope/cutoffs, snapshot manifest, run/job identities and selector hashes.
Retry readers reload that contract under current scope instead of choosing newer candidates.
The enclosing transaction must persist the binding with the pack or roll back both pack and jobs.
Legacy unbound rows refuse; downgrade cannot discard retained bindings. Initial two database
witnesses passed. Broader testing found out-of-period catalogue drift (corrected by migration
0143) and two fixture issues isolating owner-role trigger checks. The final affected 49-test run
passes, including migration round trip, catalogue equality, grants/trigger protection, downgrade
refusal without a tenant context, stable source reload and transactional rollback. These are component tests,
not an available pack command/job/API, operational close acceptance or CTL-041 completion.
Full assembly, lifecycle/idempotency, audited downloads, automatic generation, other pack kinds,
variance reporting and release/accounting approval remain outstanding.

October 8 first-close assembly: an internal assembler now reloads immutable sources and invokes
all required source/approval/journal/reconciliation/audit/report readers before constructing a
ZIP. Required paths and report identities are checked together; the source binding is included.
The scoped 79-test run passes, including real independent waiver/lock approval, freeze datasets,
audit verification and five report jobs yielding 36 verified payloads and reproducible bytes.
The witness uses seeded journal/close-run gate setup and approved reconciliation omissions;
it is not the full operational accounting close or automatic CTL-041 workflow. Unsigned
statements, pending reports and revoked permissions refuse. Re-lock assembly also refuses:
the stored raw diff does not replace the still-missing driver-variance report. No new API,
stored-file or job availability follows. Lifecycle/idempotency, encrypted storage, audited
downloads, automatic generation, other kinds, release gates and accounting sign-off remain open.

October 8 download-boundary repair: evidence-pack files now refuse generic `/files` metadata
and content access, including for all-entity Auditors. They are reserved for the dedicated
pack download route so generic access cannot bypass retained-source authorization or the
pack-specific export audit. The route is still pending. All 29 file API/access-registry tests
pass; both entity-bound and tenant-wide pack fixtures retain their destruction-scope bindings.

October 8 first-close storage: an internal completion helper now retains verified first-close
ZIPs in the encrypted file store and atomically records SUCCEEDED, file/manifest/hash and an
`evidence.finish` audit event. It requires evidence export and every source reader's permissions;
repeated completion verifies and reuses retained bytes, refusing substituted output. Database
rollback/commit and permission revocation are exercised over the existing approved-omission
close witness. Final scoped regression: 99 passed. This is not the EVIDENCE_PACK worker or a
public download: dependency scheduling, creation/idempotency, failure/cancellation lifecycle,
export auditing/API, automatic generation, other kinds, variance and release approvals remain.

October 8 queue-readiness foundation: job handlers can wait for dependencies without taking a
tenant slot or spending retry attempts. A CLOSE-specific preflight checks only immutable saved
report/job pairs, refusing failed/cancelled/missing or inconsistent sources. All 50 scoped queue,
release-fencing, stall, cancellation, registry and close tests pass. Kernel tests use probe
handlers and the source reader uses actual report jobs; the complete EVIDENCE_PACK worker is
still pending, including lifecycle/cancellation integration and API availability.

October 8 first-close worker: EVIDENCE_PACK is registered with retained-source readiness,
atomic encrypted completion and required failure cleanup. It supports first-close packs only;
unsupported kinds/re-lock variance still refuse. Job/pack locking and a cancellation guard
prevent a late cancel from marking a completed pack cancelled. Queued cancellation and an
injected pre-handler running cancellation settle unfinished packs without output. Fresh and
interrupted completion, a crash after output commit, and malformed foreign-job isolation are
covered locally. Public creation/download, request idempotency, NTF-06/automatic lock enqueue,
other kinds and variance remain open; CTL-041 and production readiness remain unclaimed.

October 8 creation command: an internal caller-authorized command now numbers and inserts a
first-close pack with its immutable sources, five report runs, six jobs and evidence.create audit
in one transaction. It requires an explicit completed audit verification and preflights retained
approval/journal/reconciliation evidence before queueing. All 55 scoped tests pass, including
rollback of numbering/rows, permissions/scope refusals, invalid verification and re-lock refusal.
This does not expose POST /evidence-packs or HTTP idempotency; the public boundary still needs
verification orchestration. Automatic enqueue/notification, downloads, other kinds, variance
and release/accounting approval remain outstanding.

October 8 first-close read/download routes: existing retained CLOSE packs now expose their
header/manifest and a verified download through API-R-42. Current source permissions/scope
are rechecked, completed stored bytes must match the retained manifest and sources, and each
successful download commits evidence.export before responding. Pending downloads, revoked or
out-of-scope access, and injected byte damage refuse. All 83 scoped tests pass; OpenAPI/client
types are regenerated and frontend type checking passes. Public creation/listing and request
idempotency, verification orchestration, automatic enqueue/notification, other kinds, variance
and current release/accounting approval remain open. No CTL-041 completion claim follows.

October 8 first-close creation API: POST /evidence-packs now atomically creates a pack and its
source jobs through the command kernel, returning the job Location and X-Erev-Evidence-Pack-Id.
An idempotent retry returns the original response and retains the original digest even when a
newer verification exists. New requests select one completed PASS covering the lock before
queueing; damaged selected bytes refuse without older fallback. A caller still needs an already
completed verification (or an authorized all-entity audit reader to run the existing verify job).
Automatic verification orchestration, listing, enqueue on lock/notification, other kinds, variance
and current release/accounting approval remain open. This is not full RPS-16/CTL-041 acceptance.

October 8 first-close register: GET /evidence-packs now lists retained CLOSE metadata with
entity/book/period/kind/status filters, id/created_at/pack_no sorting and standard cursor/count
handling. All three source-read permission scopes restrict the SQL population before pages or
counts. Unbound legacy and unsupported kinds are omitted; inconsistent bound rows refuse.
This list does not open archive files or claim integrity; individual record/download verification
is unchanged. Automatic verification/enqueue/notification, other kinds, re-lock variance and
release/accounting approval still remain open; RPS-16 and CTL-041 are not complete.

October 8 audit-job retry prerequisite: AUDIT_CHAIN_VERIFY now returns the exact verification ID
and reuses one already committed result for its tenant/job/trigger after interrupted settlement.
Both PASS and FAIL are historical results; retries neither select a newer prefix nor duplicate
verification/digest/control/notification effects. Ambiguous or mismatched results refuse under
the normal retry policy. This does not yet queue verification automatically for evidence packs,
remove their completed-verification prerequisite, or change the existing lock notification.

October 8 queued pack verification: new CLOSE requests now atomically retain a v2 binding to
one dedicated audit job alongside five report jobs and the parent (seven jobs total). Creation
no longer requires a previously completed verification. The parent waits for that exact job's
successful PASS/digest identity, and the assembler verifies its bytes/prefix/lock anchor; other
verifications cannot substitute. Failed or cancelled verification fails the pack without a ZIP.
V1 bindings and explicit-completed-verification callers remain supported. Automatic pack enqueue
on lock, completion notification, other kinds, variance and release/accounting gates remain open.

October 14 dependency remediation: a clean checkout/install found npm advisories affecting
three locked brace-expansion versions and source-map-js. Targeted updates to 1.1.21/2.1.7/5.0.12
and 1.2.2 respectively reduce npm's reported known vulnerabilities to zero for the installed
locked tree on this date. This does not constitute a full security review or release acceptance.
The repository was recovered into a persistent Documents checkout and a fresh local test database;
no previous local configuration, cloud deployment, backup-restore proof or accounting approval
is implied by that recovery. The restored backend baseline passed 52 scoped tests; patched
frontend dependencies passed 2,057 tests across 192 files, TypeScript build-mode checking,
ESLint, production build and OpenAPI staleness. Bundle-size/jsdom navigation warnings remain;
full backend, real-browser and accounting release gates are not established by these checks.

## The fifteen standing names — historical freeze record

This section preserves the cited freeze-time failures. It is not a current-main test verdict:
subsequent repairs and their dated evidence are recorded above and in the release CI notes.
In particular, the current registry includes balance aging and the loss provision register.

Fifteen tests of the backend suite do not pass in release 1.0. They are the same fifteen in every whole run on the day of the freeze, by name, and none passes when it is run again alone; the release candidate's suite shows these and no other (R-125 (n); R-126 (e)). None is skipped, loosened or marked: each fails at full strength until its cause is closed. Two gate targets fail by them, as the supervisor measured on `783f340ea`: `make answer-keys` by the six keys and `make test-pg` by the three capture witnesses. The causes below are read from the failure each test records and from the test: for names 3 to 5 as the suite takes them since index 308's part for the answer keys' runner is on the branch, for the others in the run of record on `5c3b5347c`. Names 1 to 5 are platform keys, which the suite takes on the in-memory platform. On the database platform a lane measured them on 2026-10-03 with that part: the two DISC keys pass; POS-CHK-012 compares clean in every block and is failed by its finding alone; the GT07 key is not run; POS-CHK-117 has four mismatches.

| No. | Name | Cause, as it fails | What ends it |
|---|---|---|---|
| 1 | `backend/tests/answer_keys/test_answer_keys.py::test_answer_key[DISC-S10-DISCLOSURES-REPORTS-EX21-ROLLFORWARD-AND-TIMING]` | A platform key. The suite runs platform keys on the in-memory platform, where the best outcome is "not run" and a pass needs every block compared clean on the database platform. Its four report blocks — the contract balance rollforward, the revenue from the opening liability, the disaggregation twice — are not run in memory; 99 steps applied, none refused. | The suite running its platform keys on the database platform, where this key passes (row C-12). |
| 2 | `backend/tests/answer_keys/test_answer_keys.py::test_answer_key[DISC-S10-DISCLOSURES-RPO-EX42-TIME-BANDS-AND-EXPEDIENT]` | A platform key. Its RPO report block is not run in memory; its contracts block compares clean; 117 steps applied, none refused. | The suite running its platform keys on the database platform, where this key passes (row C-12). |
| 3 | `backend/tests/answer_keys/test_answer_keys.py::test_answer_key[DLT-CHK-020-CHK-022-GT07-JANUARY-2023-GROSS-AND-DELTA-JOURNALS]` | Updated October 8: full canonical database run applies 141 steps, then cannot complete the nondistinct review for CONTRACT-1 / POB #3. The fixture lacks the integration target required by that review; 57 later steps are refused and no checkpoint blocks compare. Supported POL-122 overrides are no longer the first blocker. | Extend the fixture/runner with explicit supported distinctness facts, preserving the intended journal oracle. Dated evidence: REPOSITORY-CHECKS-2026-10-08.md. |
| 4 | `backend/tests/answer_keys/test_answer_keys.py::test_answer_key[POS-CHK-012-S9-PRESENTATION-NETTING-PER-CONTRACT]` | A platform key that declares two policy overrides. In memory every block compares clean, 108 steps applied; the outcome is "not run — databases not provisioned", and the message ends with the same finding, for its two overrides of POL-122. | The next release's road for POL-122 (row C-2): on the database platform the key compares clean in every block and is failed by its finding alone. R-126 (c). |
| 5 | `backend/tests/answer_keys/test_answer_keys.py::test_answer_key[POS-CHK-117-BALANCE-AGING-EXPORT-TIES-TO-RECLASS]` | A platform key that declares three policy overrides. Its balance aging block is not run: "RPS-12: balance_aging builder is not registered; CTR-14: fx_layer_movement is not persisted"; 94 steps applied; the message ends with the same finding, for its three overrides of POL-122. | The balance aging builder (row C-11) and the road for POL-122 (row C-2). On the database platform the key has four mismatches, the same with its overrides created and approved as without them — an unbilled receivable of 3,000.00 expected and none stated, a contract asset of 2,000.00 expected and 5,000.00 stated — which is what the unconditional right the key declares would move; not traced. R-126 (c). |
| 6 | `backend/tests/answer_keys/test_answer_keys.py::test_answer_key[VC-CHK-113-TC-POBVC-16]` | Seven checkpoint mismatches between the key and the engine on a price concession after a modification (row A-3). | The reviewer's decision on AD-14 and AD-15 (row A-1). |
| 7 | `backend/tests/domain/answer_keys/test_platform_pos117_balance_aging_db.py::test_pos_117_balance_aging_cells_from_the_unregistered_builder` | The balance aging builder is not registered, and called directly it leaves cells of key POS-CHK-117 unmatched: first, row `contract:C-POS-117:UNBILLED_RECEIVABLE`, column `bucket_0_30`, expected 3000.00, absent. | The balance aging builder (row C-11), with its key's plan (name 5). |
| 8 | `backend/tests/domain/demo/test_volume_generator.py::test_small_scale_through_commands` | The volume dataset at one-thousandth scale is refused by the product's own bound on a delivery: "validation-failed: VOL-C-000001, obligation POB-01 (VOL-P-0007): requested 7, remaining 3." The seed at full scale passes. | The rest of the performance phase (row C-10). |
| 9 | `backend/tests/domain/platform/test_audit_coverage.py::test_req_plt_019_categories_covered` | One category of audited actions has no observed action: "AI proposal lifecycle (pending on lane F-AIX)". The test stays red by design until the feature writes its events (R-50 (f)). | AI assistance (row C-15). |
| 10 | `backend/tests/domain/reports/test_analysis_reports.py::test_balance_aging_chk_010` | The run is refused: 422, rule API-R-41, "This report is not available yet." (row B4-6). | The balance aging builder (row C-11). |
| 11 | `backend/tests/domain/reports/test_registers_close.py::test_out_of_period_register_k07` | Updated October 7: the test drives the import child worker and the report reads its stored LATE_EVENT finding. The EUR 100,000 invoice is separate from zero posted effects; uploader, approval, cutoff and period/book filters are checked. | Implementation complete; current verification is recorded in PROGRESS.md. Secondary-book finding coverage and prior-date balance classification remain limited under B4-7. |
| 12 | `backend/tests/domain/reports/test_registers_judgement.py::test_loss_provision_register_k03` | The run is refused: 422, rule API-R-41, "This report is not available yet." The loss provision register is not registered: its source is not stored. | The loss provision register's builder (row C-11). |
| 13 | `backend/tests/pg/test_migration_capture_pg.py::test_import_job_creates_the_confirmed_prerequisites_over_wld_f_15[identity-mapping]` | The test's world lacks a fiscal period: "The dry-run computation of Contract 3 ended refused: ENGINE_INVARIANT_VIOLATED: no accounting period of the entity contains the date; the import captures nothing for it." The repair is a one-line edit of the world, which a lane's session was refused and which nobody takes over (record 6; R-44 (d); R-109 (f)). | A permission only Ray gives (R-126 (a)). |
| 14 | `backend/tests/pg/test_migration_capture_pg.py::test_import_job_creates_the_confirmed_prerequisites_over_wld_f_15[non-identity-target]` | As name 13. | As name 13. |
| 15 | `backend/tests/pg/test_migration_capture_pg.py::test_import_keeps_an_existing_ssp_only_product_over_a_second_label` | As name 13. | As name 13. |

Beside the fifteen, a whole run of the suite reports three expected failures and one skip. The three are strict pins that stood before the freeze: each is marked as an expected failure and fails the suite on the day it passes, so that its mark comes off with the change that closes it. They are `backend/tests/domain/platform/test_sandbox_replay.py::test_replay_reaches_the_source_lock_chain` (row B7-8; ruling R-10); `backend/tests/domain/reports/test_historical_line_cutoff_db.py::test_historical_read_excludes_a_line_posted_after_the_stamp` (row B4-11); and `backend/tests/engine/s13_books/test_s13_deposit_fold.py::test_q11_invoice_dated_t_while_not_a_contract_observation`, an observation for the reviewer (AD-33 of the review package; row A-1): with a receipt of 1,200.00 while the arrangement is not a contract, and an invoice of 1,200.00 dated on the day the criteria are met, the engine states a contract liability of 1,200.00 against the open receivable, and whether an invoice raised before the contract exists may create a receivable and a contract liability at all is the reviewer's question. The skip is by design: `backend/tests/domain/contracts/test_modifications.py::test_tc_rep_01_shipped_state_sixteen_obligation_versions` is the build specification's name for a case that runs in the parity suite.

## Sentences of the governed documents that say more than the product does

No governed document is changed for release 1.0 by this file. Where a sentence of the PRD, the requirements, the data model, the policy catalogue, the engine specification, the screens' specification or a guide states more than the product does, the product as built governs for release 1.0, and the sentence is named here. The withdrawal of policy overrides (row B1-1) and the refusal of index 309 (rows B3-13 and B3-21) mark their own rows in those documents and are not repeated.

| Where | The sentence | What the product does | Row |
|---|---|---|---|
| `docs/02-PRD.md`, BR-CLS-06; `docs/guides/user-guide.md`, "Posting into a reopened period" | "In a `reopened` period, every posting command (import, manual event, manual adjustment, journal run) needs a human approval by a user other than the submitter; auto-approval rules do not apply". | The nine kinds of command of row B1-2 post into a reopened period on their sender's word. | B1-2 |
| `docs/03-REQUIREMENTS.md`, REQ-RPT-003 | "rollforward closing = GL balance (when a trial balance exists)". | The tie-out is answered as not applicable whether or not a trial balance exists. | B4-4 |
| `docs/03-REQUIREMENTS.md`, REQ-RPT-009 | "The 50-14 and 50-14A exemptions apply only where elected". | The elections of POL-199 and POL-200 exclude nothing. | B4-3 |
| `docs/03-REQUIREMENTS.md`, REQ-REF-012 | "Disaggregation attributes configured as mandatory must be set before a product is usable". | No command refuses a product that lacks them. | B1-16 |
| `docs/03-REQUIREMENTS.md`, REQ-JE-016 | "Batches not acknowledged age on the close cockpit". | Nothing reads the setting that would age them. | B1-17 |
| `docs/03-REQUIREMENTS.md`, REQ-PLT-034 | Signed webhook deliveries for six kinds of event. | Two kinds are delivered. | B8-8 |
| `docs/04-DATA_MODEL.md` and `docs/accounting/ENGINE_SPEC.md`, the legacy-parity preset | The four obligation templates of a legacy import are called seeded. | Nothing seeds them. | B5-8 |
| `docs/04-DATA_MODEL.md`, §16.3, "The usage period of a report" | "a report dated after its period's end is accepted as before". | True as written. What it leaves unsaid: a report dated in a later accounting period puts the fee's revenue into that period. | B5-2 |
| `docs/design/SCREENS_B.md`, §3.2 | The rows' "Retry export" are the way "until" the API's `export` retries the failed batches of a run. | As recorded: the condition is met, and the header of a failed run still does not offer "Retry export". | B.9 |
| `docs/design/SCREENS_B.md`, §5.6.1 | A warning on the rollforward's "Other" row. | Not built. | record 18 (ii) |
| `docs/02-PRD.md`, ACT-44, against `docs/04-DATA_MODEL.md`, API-R-13 | Who authors the security, platform and AI settings. | The two documents differ, and the question is not decided. | record 31; R-124 (e) (3) |
| `docs/02-PRD.md`, NTF-08; `docs/03-REQUIREMENTS.md`, REQ-PLT-021 | A notification of a close blocker. | Raised nowhere. | B8-12 |
| `docs/02-PRD.md`, IMP-145 | The sentence stands as the API says it. | Its second road is on no screen. | R-124 (g) (8) |
| The operator's `resend-invitation`, in five places | The command is refused for a member. | Measured: it issues the member's invitation again. | record 31 |
| `docs/accounting/POLICIES.md`, POL-015, POL-026, POL-142 and POL-231 | Each row states a value, the levels it can be set at and what it decides; POL-142 states a test of a renewal commission against the initial one. | No rule of the engine reads any of the four: a stated value changes no figure. | B3-22 |
| `docs/accounting/ENGINE_SPEC.md`, S02-R-12 | POL-015 "only permits portfolio-scope estimate versions". | No rule reads POL-015, and the product builds no estimate version for a portfolio. | B3-22 |
| `docs/04-DATA_MODEL.md`, API-S-PolicyResolution; `docs/guides/user-guide.md`, "Policies" | The resolve read "answers the value in force for a scope", and the source of a resolution may be a product or an obligation template version. | The read consults neither. | B3-23 |
| `docs/04-DATA_MODEL.md`, T-REF-20 `policy_values` (rev 1.323, its first sentence); `docs/dev-guide.md`, DG-KRN-REG-02 (rev 1.300, the clause's title); `docs/build-spec/13-reference-contracts-data.md`, RFD-9 (rev 1.82) | "a value that no computation reads is not stored"; "a level P value that no computation reads is refused". | The refusal holds for three parameters (rows B3-13 and B3-21). A value of the four that no rule reads at any level is stored and published as before (row B3-22). Each passage says so in the sentences behind its first; the first, read alone, says more. | B3-22 |
| `docs/01-DECISIONS.md`, D-25a; `docs/GLOSSARY.md`, "FX layer" | "An approved contract-level override may treat refundable advance consideration as monetary, remeasured at the closing rate, in the ASC606 book." | No policy override can be created, so the exception is not delivered: POL-163 takes the value set for the legal entity. `docs/03-REQUIREMENTS.md` REQ-FX-002 says so; these two sentences were left as they stand. | B1-1 |
| `docs/design/SCREENS.md`, §15.7 | The delegate choices are read from `GET /approval-delegations/delegates?q=`, "so "New delegation" opens for every member who sees the screen". | The read is not built, and the paragraph's interim state stands: the choices come from the member directory, which needs `user.manage`. | B6-8 |
| `docs/design/SCREENS.md`, SCR-IA-01, the rail's row "Approvals" | The destination's badge is the "count of `PENDING` requests where `can_decide = true`". | The rail takes the count and no screen gives it one, so no badge shows; the same count stands beside the tab "Waiting for me". | read on main at `b8f4b9e29` |


## October 14, 2026 — automatic first-close preparation

Lock approval now queues a durable EVIDENCE_PACK/PREPARE_CLOSE job in the lock transaction.
After commit it prepares the retained CLOSE pack and seven source/build jobs atomically. The
build job's parent_job_id associates it with preparation; a post-commit crash reuses the same
pack without creating another set of source jobs. SYSTEM source capabilities are limited to the
validated lock entity. Cancellation before preparation creates no pack; after creation, the
preparation job cannot be cancelled and the pack build has its own cancellation lifecycle.
Preparation success is not archive availability. Existing lock notices promise stored snapshots;
NTF-06 availability notification is still pending. Re-lock preparation refuses without the
variance report. Other pack kinds, report-catalogue PACK builders and operational CTL-041
acceptance remain incomplete. Local tests use seeded journal/close-run gates and do not prove
operational accounting acceptance. No deployment or independent accounting approval is claimed.

Validation for this change: lock-module and retained-binding regression **81 passed in 183.79
seconds**; source Mypy and changed-file Ruff lint/format pass. This is scoped evidence, not a
current full backend, browser, release, or accounting acceptance result.


## October 14, 2026 — automatic first-close availability notification

Approval-driven locks now defer NTF-06 until the automatic pack's archive is retained. The
PERIOD_LOCKED notice and archive metadata commit atomically, using the lock as notification
subject and the period cockpit as link. Current active Controller, Revenue Reviewer and Auditor
roles must cover the entity. Manual builds do not notify, and a retry after successful retention
does not repeat the notice. Generation failure/cancellation produces no availability claim.
Sandbox replay's separate snapshots-only notification is unchanged; no replay pack is claimed.
The focused four tests passed, including scoped recipients, rollback after notification insert,
post-commit crash reuse and cancellation. Broader lock/notification regression: **54 passed in
196.55 seconds**. Source Mypy and changed-file Ruff lint/format also pass. These scoped checks
do not establish current full-backend, browser or release acceptance.
Seeded close/journal gates remain in the focused fixture; operational CTL-041 and independent
accounting approval are still missing. Re-lock variance and other pack kinds remain incomplete.


## October 14, 2026 — operational first-close manifest control witness

`backend/tests/domain/reports/test_evidence_packs.py::test_ctl_041_close_pack_manifest` now
exists with the CTL-041 marker and passed in 18.51 seconds. AVM-US September 2026 runs through
close execution, journal calculation/approval/export/acknowledgement, both reconciliation
workers and distinct preparer/reviewer sign-offs, lock approval, automatic pack preparation,
audit verification, supporting reports, archive retention and an Auditor's API download.
No journal, close-run result, current-period gate result or reconciliation review is seeded;
no current-period gate is waived. The archive names the actual journal run and both reviewed
reconciliations. Required paths, payload hashes, separate manifest hash and rejection of altered
payload/manifest bytes are checked.

Boundaries: earlier periods are closed as fixture state; the ERP acknowledgement uses the test
adapter, and the uploaded GL is a synthetic matching reference derived from the comparison.
This tests workflow/evidence integrity, not independent financial reconciliation or correctness
of all accounting amounts. It supersedes the earlier missing-CTL-041-witness notes for this
first-close case. Re-lock variance, other pack kinds, full controls/current release verification,
real-browser acceptance and independent accounting approval remain outstanding. No deployment
or production-readiness claim follows from this targeted control pass.


## October 14, 2026 — first-close evidence screens and control gate

The first-close register/detail screens and verified ZIP/manifest downloads are implemented.
The manifest download returns the retained archive's exact bytes, with the same scoped export
permissions and audited completion as the ZIP. List metadata includes retained entity/period
labels, file count and manifest hash; it is not an archive-integrity verification. The final
API/worker/MFA/schema/metadata regression passed 118 tests; focused UI tests passed 12. A full
frontend run passed 2,069 tests before the final count/hash columns; those columns also passed
focused tests, TypeScript, lint and build. This does not close RPS-20: auditor-request actions,
generation forms, other kinds, remaining register details and real browser acceptance remain.

The separate immutable c214c47 control run passed all 497 tagged tests, covering 47/49 controls.
CTL-045 and CTL-048 remain missing, so the control gate fails. Details and binding are recorded
in CONTROLS-2026-10-14.md. No full release, independent accounting sign-off or production
readiness is claimed, and no deployment was performed.


## October 14, 2026 — auditor request navigation

The evidence workspace now includes A-01 through A-20 with report sources, context-preserving
navigation, selected-period reconciliation access and the viewer's own audit-event filter.
Report actions are only offered for definitions returned by the API. Contract sample,
access and change generation remain unavailable; their visible actions do not submit placeholder
commands. The service-organization-report row explicitly identifies that external deliverable.
The catalogue now links to the actual evidence workspace and requires its read permissions.
RPS-20 still needs generation workflows, remaining presentation and real browser acceptance.


## October 14, 2026 — first-close evidence generation form

The evidence workspace now exposes the existing CLOSE creation API through an explicit
entity/book/period/retained-lock form. It enforces the intersection of export/source scopes,
reads historical choices across pages, and retains the original idempotency key when an
uncertain request is retried. It offers only first-close locks with retained snapshot metadata.
Historical inactive entities/books remain selectable; the server remains authoritative for
source validity. Re-lock variance, contract sample/change/access generation and real browser
acceptance are still unfinished. No new backend accounting behavior or deployment is included.


## October 14, 2026 — first-close contents presentation

The detail screen now lists required first-close sections and missing filenames using the
retained manifest, exposes the retained lock ID, sorts payload paths, and offers named,
keyboard-accessible hash-copy controls. Presence is distinct from archive verification;
the download boundary continues to verify original bytes and retained sources. The manifest
is separately hashed, not listed inside itself. Re-lock variance, other pack kinds, remaining
presentation and actual browser acceptance remain outstanding; this does not complete RPS-20.


## October 14, 2026 — evidence metadata read audits

Register and detail HTTP reads now commit evidence.read before returning no-store responses.
Register facts describe only the authorized returned page; detail facts bind the pack's
retained lock/status/hash. Failed reads do not record successful access. This closes the
read-audit gap in SF-09 but does not implement the outstanding pack kinds or re-lock variance,
and does not supply independent accounting approval or complete release verification.

## October 14, 2026 — first-close browser acceptance

A focused real-browser test now passes for generation from a retained first-close lock,
contents display, manifest digest comparison, manifest/ZIP downloads, and light/dark
accessibility. The initial full closed-world run passed nine tests and failed the new test
on the register link target size; the link was enlarged and the focused retry passed.
This uses the retained local demo world and does not establish a passing fresh full-browser
or release gate. Other pack kinds, re-lock variance, remaining RPS-20 acceptance and
independent accounting approval remain open. See PROGRESS.md for exact evidence.

## October 14, 2026 — fresh closed-world browser gate

The fresh immutable closed browser project passed all 10 tests on 3e60e6a, including
first-close generation, retained downloads and light/dark accessibility. This supersedes
the earlier absence of a passing fresh closed-world gate. Other browser projects,
subsequent backend changes, re-lock variance, other pack kinds and independent accounting
approval remain open. The gate discarded screenshots with its temporary context; JSON
results are retained, but screenshot retention needs repair. See
[BROWSER-2026-10-14.md](BROWSER-2026-10-14.md) for exact scope and source binding.

## October 14, 2026 — browser artifact retention repair

New gate runs retain screenshots and failure traces beneath the report's relative
`artifacts` directory, separated by invocation number and project. Runtime session state
is isolated and removed on completion. Regression tests exercise success, failure, repeat
runs and immutable-context removal; a real Chromium probe verifies capture/trace output.
This repairs the retention mechanism but does not recover the earlier gate's deleted
screenshots or establish another application acceptance run.


October 15 computation evidence: revision 0160 now retains encrypted full typed inputs and
canonical outputs for newly persisted computations, with original digests, logical hashes,
book coverage, ledger positions before posting, and predecessor identity. Fourteen database
regressions pass, including the close/reopen/re-lock flow, failed-storage rollback, idempotency,
typed replay, retained-file holds and generic download denial. This is source retention, not
completion of replay or release validation: historical computations are not backfilled, the
T-CON-26 verification workflow remains absent, and RPT-38 still needs replay orchestration
and driver attribution. Current-candidate recovery and full-suite evidence remain required.


October 15 verification persistence: revision 0161 supplies the validation/attempt/group
and immutable result tables. The internal writer now persists task-fenced decisions and
accepted pointers atomically with a contract-keyed audit event. ERROR evidence remains
unaccepted for retries; moved source heads and stale task/release identities are refused.
This does not supply the public verification workflow: selection creation, fan-out/handler,
dataset publication, historical backfill and release admission remain outstanding.
The earlier full CI on frozen 3cf8f5b ended with 22 failures and requires current-main triage.


October 15 AI audit coverage update: all ten implemented AI command routes now participate
in the shared catalogue and command walk. The full CTL-038 walk, all fourteen audit categories,
and focused AI walk pass (CI-2026-10-15.md). This supersedes the historical pending AI-category
failure recorded above. Proposal evidence in these scenarios is synthetic; model accuracy,
remaining AI workflows and full release-candidate verification are not established by it.

## October 19, 2026 — frozen monetary changes in re-lock evidence

Re-lock evidence now includes a separate `relock/frozen_measure_changes.json` payload.
It compares verified frozen revenue, liability, contract asset plus unbilled receivable,
and disclosed RPO by contract and currency, with exact arithmetic and retained source
identities. It refuses unordered/mismatched lock scopes, missing datasets, altered bytes,
invalid monetary cells and duplicate identities. It never assigns the difference to a
guessed driver. Original stored re-lock evidence is still verified and delivered unchanged.

This is the monetary endpoint portion of RPT-38, not the completed report. Ordered
event replay for driver attribution, report registration/exports, cell explanations,
browser acceptance and the real K-03 financial acceptance remain outstanding. The
seven previously listed missing report builders remain unregistered. No deployment or
independent accounting sign-off is claimed.

## October 19, 2026 — event-only variance replay core

The new `variance_replay` service runs the engine with DRY_RUN inputs, orders added
immutable events by ENG-06, evaluates each maximal driver run and reconciles its
exact effects to both supplied frozen endpoints. It records execution hashes and
all contributing event keys. Time progression has a separate step. Endpoint mismatch
is an error, never a balancing OTHER amount. Unknown classifications are refused.

This service is not yet called by a report or job. Callers must still obtain authorized,
verified retained bundles and implement the fixed-period metric projection. Changed
references, FX rates, membership and posting basis currently require separate phases;
the service refuses them rather than mixing their effects into event attribution.
The real-engine case covers two late billing events (liability 20 -> 170, change 150),
not the complete K-03 financial acceptance. Nine focused tests, Ruff and Mypy pass.
Seven report builders remain unregistered; production readiness is not established.

## October 19, 2026 — fixed-period variance monetary projection

The event replay now has a server-owned `replay_period_money` entry point. Its
projection reads revenue from the signed posted basis plus engine posting intents
in the requested posting period; a prior origin period does not move the posting.
Contract liability and contract asset plus unbilled receivable come from the selected
period's engine balance rows. Transaction and functional currency views use the
retained currency scale and exact fractions. Scope, currency, duplicate balance
identities and missing money values are checked; schedules are not used as revenue.

The real-engine late-invoice case now runs through this adapter. Fifteen focused
checks pass, including signed posted/intent arithmetic and refusal cases; Ruff and
Mypy pass. This still is not the report/job pipeline. Dated RPO, authorized retained
source selection, reference/FX/membership/posting-basis replay and report/UI remain
open. No missing report builder is newly registered; no deployment or full financial
acceptance is claimed.

## October 19, 2026 — dated RPO in variance replay

RPO now uses the existing dated trace reader, with transient in-memory row keys and
no persisted contract/version writes. It reads scheduled and awaiting remainders at
the selected period end, applies contract status and disclosure-entry dates, and
uses retained duration/right-to-invoice exemption policies. Every replay projection
receives the bundle actually executed, including newly admitted activation events.
Amount-specific VC exemptions still require dated exclusion evidence and refuse;
foreign-currency functional RPO also refuses without a supported valuation basis.

Real-engine coverage proves a May delivery leaves April RPO at 795 and moves May
RPO to 736.16, with +58.84 revenue and -58.84 RPO reconciled under LATE_EVENT. It also
covers activation during replay, duration exemption and missing-trace refusal.
Nineteen scoped tests, Ruff and Mypy pass. This is not K-03 financial acceptance or
a completed report. Authorized retained-source loading, reference/FX/membership/
posting-basis replay and report/job/UI remain open; seven builders remain unregistered.
No deployment or independent accounting sign-off is claimed.

## October 19, 2026 — frozen-close and computation source read phase

`variance_sources.read_pair` loads verified frozen closes and retained computation
candidates for their monetary contract population. Computation input/output files
are checked by the existing evidence reader, including source hashes, runtime,
stream heads, predecessor and complete group/entity authorization. Missing evidence
is never reconstructed from current data. Required access entities are returned
for later run/rerun authorization. A no-new-event recompute is filtered by actual
computation cutoff/creation before latest-version selection, preserving older reads.

Frozen monetary data requires report.run; the existing evidence-pack reader still
also requires audit.read. Authorization precedes file access. Five focused frozen
source/permission/regression tests pass, plus one actual retained-computation test
showing old/new selection across a no-new-event recompute. The latter uses a synthetic
frozen-population shell to isolate selection, not a complete accounting close.
Implementation Mypy and changed-file Ruff pass. A candidate must still reproduce
frozen endpoints; job integration, operational input normalization, remaining replay
phases, report registration/UI and independent financial acceptance remain open.
No additional report builder is registered, and no deployment is performed.

## CHANGE/ACCESS evidence workflow — October 19, 2026

- Added atomic API creation, retained child-report readiness, current-requester worker
  authorization, encrypted final archives, scoped list/detail and verified ZIP/manifest downloads.
- Reporting now offers change/access generation forms, kind filters and retained detail pages.
  CHANGE uses inclusive dates; ACCESS requires tenant-wide evidence and access.approve grants.
- Real API → report workers → parent worker → list/detail/download passes for both kinds;
  retained repeat downloads keep original bytes. Targeted UI flows, types and lint pass.
- Still open: populated review campaigns through the complete parent flow, cancellation/revocation
  acceptance specific to these kinds, and wider RPS-16 accounting acceptance. Next reporting
  development: catalogue PACK builders and disclosure orchestration; remaining forecast work.
  No deployment or production-readiness claim.

## Catalogue evidence source/output adapter — October 19, 2026

- RPT-54/55 now have an internal adapter for an explicitly selected retained pack. It binds
  exact selectors, entity scope, source cutoff, source hash and pack/job identity; reauthorization
  refuses changed sources and requires current evidence permissions in every source entity.
- ZIP output preserves the complete original archive. Sample PDF/XLSX extraction preserves the
  retained chapter bytes and emits provenance linking the artifact to the pack manifest.
- Five focused archive/format checks pass; actual closed-period pack binding/read, altered-source
  refusal and revoked-export refusal pass. Ruff/Mypy pass.
- This is an internal adapter, not catalogue availability: ordinary report creation, persistent
  binding and dependency dispatch still need integration. The catalogue still refuses these codes.
- Reinspection confirms disclosure_pack already has child orchestration and a worker execution
  path. Its remaining acceptance gaps need auditing; do not describe orchestration as absent.
  No deployment or readiness claim.

## Catalogue evidence dependency/execution chain — October 19, 2026

- Ordinary report insertion now prepares and persists an explicit source pack binding in the
  initial INSERT, atomically with its jobs. Immutable report parameters/entity scope are not
  updated later. Retained preparation reuses the same pack; selectors and cutoff remain fixed.
- REPORT_RUN readiness waits for the exact EVIDENCE_PACK job and verifies its subject/hash.
  The worker rehydrates the current requester, verifies source access and stores the original
  artifact plus provenance through normal report completion/control recording.
- Real close acceptance exercises internal report creation, child reports/audit verification,
  source-pack completion and catalogue report worker completion; output bytes/hash match.
  Ruff and Mypy pass. Sample orchestration acceptance remains open.
- Public catalogue admission is still disabled: registration, lock resolution, source contracts
  and addressed/list/download authorization must be integrated before exposing RPT-54/55.
  Fresh sample capture currently requires the creation-time known_at; historical fresh capture
  remains unsupported (retained reruns preserve the original cutoff). No deployment.

## Public period evidence catalogue report — October 19, 2026

- Registered period_evidence_pack through POST /report-runs. Lock selectors reconcile to the
  frozen entity/book/period and cutoff; declared evidence permissions govern admission/scope.
- Standard list/detail/output/rerun and idempotent replay paths check current source access.
  Lists filter before counts/cursors. Direct framework output reads also reauthorize sources;
  generic file routes remain restricted to their existing report-output route.
- Same-source reruns preserve the bound evidence pack and original archive, with explicit
  provenance. Failed-pack metadata can still be authorized; readiness/download reject failure.
- Actual public API creation, dependencies, worker output, list/detail/download, limited-user
  denial and original-source rerun pass. Existing report lifecycle/rerun regression passes;
  Ruff/Mypy pass. User guide updated.
- Next: contract_sample_pack public catalogue admission and full sample orchestration acceptance;
  fresh historical sample capture and wider accounting/re-lock acceptance remain open.
  No deployment or production-readiness claim.

## Public contract sample catalogue report — October 19, 2026

- Registered contract_sample_pack with ZIP/PDF/XLSX and the complete evidence permission set.
  Catalogue creation uses the existing source-pack dependency, worker and current-source read
  authorization; source-document permissions still apply to metadata, lists and downloads.
- Threaded optional known_at through sample creation into the existing historical collectors.
  Generation timestamps stay current. Same-source reruns preserve the bound original artifact.
- Real K01 API → source pack → report worker → download/rerun passes for all three formats.
  A later attachment appears in current capture but not in historical PDF/XLSX sources;
  missing SSP-document permission hides rows before count/cursor, and revoked grants refuse
  downloads. Sixteen source-contract checks and Ruff/Mypy pass.
- Catalogue audit: 58 registered report codes; forecast_outputs is the remaining unregistered
  code. This is registration coverage, not full accounting or release acceptance. Next:
  forecast_outputs entry-point integration; broader multi-contract/re-lock/report acceptance
  and independent accounting sign-off remain open. No deployment or readiness claim.

## Public forecast catalogue reports — October 19, 2026

- Registered forecast_outputs for JSON/CSV/XLSX through ordinary POST /report-runs and
  REPORT_RUN execution. Creation pins the completed publication before INSERT; execution
  reauthorizes the requester and renders all five saved sections without recapturing sources.
- Read/detail/list/download and cached-command access use current scenario/source grants.
  JSON data reads also authorize the bound publication. CSV remains a five-section ZIP;
  output_sha256 follows the forecast convention of hashing the canonical five-section dataset.
- Same-source catalogue reruns preserve the publication and dataset hash. Original forecast
  computation reruns remain explicitly unsupported; the UI/API must not imply recomputation.
- Real API creation, worker execution, download and rerun pass for all three formats; removal
  of scenario.use refuses retained-source access. Twenty-four focused source/export checks
  and Ruff/Mypy pass. User guide describes saved scope, format retention and hash semantics.
- Catalogue audit: all 59 definitions now have registered execution paths. This is not full
  report content, populated business workflow or independent accounting acceptance. Next:
  audit reporting feature/content gaps and complete the outstanding workflows, including
  multi-contract samples, reopen/relock, forecast comparisons and report-centre usability.
  No deployment or production-readiness claim.
