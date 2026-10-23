# Current development scope

Owner scope confirmed October 22, 2026. This is the current development index, not a
certificate that every historical limitation has been resolved. Dated checkpoints in
LIMITS-1.0.md and BUILD-HISTORY remain evidence, not a cumulative list of unfinished work.

## Delivery boundary

Finish the repository for public publication under its existing noncommercial license.
Prioritize features and targeted verification. Publish reviewed changes directly to main;
do not deploy. Migration into live business, exhaustive approval workflows, sandbox lock
history reproduction and independent accounting sign-off are not development gates.
Keep critical financial permissions, segregation of duties and audit evidence. Sandbox
refresh from production must preserve isolation and allow experimentation.

## Reporting implementation status

### Sequential modification causal analysis — owner-selected scope

On October 22 the owner chose original-event-order recomputation, explicitly labelled causal
analysis and reconciled to the period total. This replaces the previous requirement to assign
unique original posted functional amounts to individual events. Do not change posting or FX
semantics to manufacture such ownership.

The register already has native event TP/catch-up/components, analytical spot equivalents,
source drill, and a limited original functional calculation path for an exclusively explained
period. These remain distinct from the new causal analysis. Close variance already supports
individual event replay; the modification register integration is implemented below.

Implement the selected mode using authorized retained computation inputs and fixed reference,
currency and reporting-period bases. Replay events in effective-date/record-sequence/key order;
retain each signed change and executed input/output hashes. Preserve positive and negative
changes even when their net is zero. Reconcile baseline plus modification and other event effects
to the reproduced final period amount, showing other effects explicitly rather than assigning
them to a modification. Labels and cell evidence must say causal analysis, not posted ownership.

Execute engine calls outside database transactions, with worker heartbeats. Saved report reruns
must use their bound results, and source access must cover the full computation group. Keep old
saved reports unchanged.

Implemented in the register through Currency amount basis → Sequential causal analysis
(`currency_basis=causal_analysis`). The worker authorizes retained original computations and
requires all entities in a computation group to be selected. It calculates outside SQL
transactions with heartbeats, retains per-step hashes, and rechecks requester access before
saving. Baseline includes the fixed original posted history; it is not an opening balance.

Transaction, functional and reporting views show baseline, individual selected modifications,
other events and final period revenue. Signed zero-net changes remain separate; reporting uses
pinned period-average rates. Approved but unapplied modifications show an explicit unavailable
row. Separate-contract bookings can show an explicit zero before activation. Amount cells show
retained calculation evidence. Existing saved reports retain their earlier shape and semantics;
causal reruns rebuild the saved results without rerunning the engine or reading current amounts.
Migration 0335 freezes catalogue/schema metadata for the new option.

Necessary verification: nine native causal cases (including USD/GBP effects, reporting,
offsetting changes and a delivery between modifications); 40 existing variance replay cases;
two populated database workflows, including public runs/cells in all three views, a later second
modification and equal-output retained reruns, plus separate-contract booking; ten frontend
parameter/drill cases; scoped lint/types and catalogue checks. These are bounded examples,
not proof of every contract/currency combination. Original posted event ownership is no longer
required for this owner-selected causal-analysis feature.

### Mixed original sources — aggregate presentation implemented

The owner selected net revenue totals with complete original source membership, without
inventing individual layer amounts. BBR revenue cells now retain verified transaction and
functional ledger totals, source contract/layer/date/key identities, prior postings and evidence
hashes. Scalar histories verify independently of source ownership, including mixed TIME/EVENT
inputs. Source identities carry no net amount. Saved reruns preserve this evidence; older reports
keep their prior drill. Missing original evidence is explicitly unavailable. Source details are
withheld when they span entities outside the viewer's access scope. Migration 0336 records IPE.

Necessary verification: two populated multi-deposit agent workflows, including a combined
contract, public BBR cells and identical retained cell reruns; 50 revenue-trace/BBR unit cases;
eight catalogue cases; populated migration/catalogue parity and scoped lint/types pass.

Gross-control aging continues to use actual gross sources. Per-layer net allocation and finer
within-period TIME/EVENT ownership remain deliberately unavailable where native evidence does
not determine them; the owner-selected aggregate presentation does not assert such ownership.

### Royalty correction after collectibility exit — implemented

The owner selected reductions of already recognized income, with no new income while excluded.
Stage 09 now revisits previously recognized usage periods in original event order, allowing the
1,600 to 1,400 correction while preserving the frozen licence satisfaction and minimum guarantee.
Upward corrections, later satisfaction and newly reported usage periods cannot create income;
an upward revision after a reduction does not re-recognize that reduction before re-entry.
Trace nodes retain the actual statement/estimate inputs of the reduced target. Existing same-day
re-entry behavior is retained. See ROYALTY-EXIT-CORRECTION.md for bounded verification.

## Implemented priorities, with bounded claims

- BBR reporting currency: all four measures translate original functional amounts at pinned
  entity-period averages, with signed source rounding tied to period totals. Journal revenue
  uses the same aggregate conversion basis; retained cell evidence names rates and original
  functional amounts. Foreign-entity report/cell/rerun and signed rounding checks cover this path.

- Modification amount drill: new report cells rebuild saved inputs and open original native
  calculation nodes where retained. Analytical spot/reporting equivalents list their pinned
  rates separately. Missing source identity in older runs requires a new report; amounts are
  never taken from today's modification. This adds navigation/evidence, not per-event posted
  functional ownership.

- Close-variance event detail: an opt-in mode now evaluates each business event in original
  order, retains signed differences, preserves offsetting effects and reconciles driver totals
  and frozen endpoints. Functional positive/negative same-period modifications are covered,
  including net zero. Membership/reference/population phases retain explicit boundaries.
  This is causal replay attribution, not original per-event journal-line ownership; the latter
  is outside the owner-selected causal-analysis scope described above.

- RPO: royalty remainder and targeted VC exclusions, fixed guarantee retention, separate
  partial-exemption rows, rollforward and close-variance projection, currency rounding and
  retained bindings. Missing exact dated royalty evidence still requires recomputation.
- GL reconciliation: balance plus document CSV/XLSX uploads, shared connector/file difference
  attribution, retained comparisons and role-level report reconciliation. Document amounts
  are not added to closing balances.
- Billing reconciliation: post-lock invoices enter the first later period open at receipt on
  both sides; origin periods persist in differences and sign-off evidence, and new late documents
  invalidate reviewed comparisons. See LATE-BILLING-RECONCILIATION-2026-10-23.md.
- Combined-contract aging: original receiving-contract aging and separate member allocation
  adjustments.
- Sandbox: production refresh and editable isolated periods; production lock-history replay
  is outside the requested scope.

The revenue waterfall now aligns whole selected intervals by actual dates across calendars.
Identical dates can combine different local period keys; different dates get separate columns
and entity-specific contributor populations. Aligned layouts keep fiscal labels; older saved
runs preserve their earlier interpretation. This does not reallocate partial fiscal periods
into common calendar months. Other reports with calendar-compatibility guards still require
separate implementation and must not be enabled by simply removing those checks.

These statements do not prove every combination of contracts, currencies, calendars and
lifecycle events.

## Forecast publication re-export

Original forecast publications now accept the report rerun API as well as the existing UI
catalogue re-export flow. The API first verifies the original publication identity and digest,
then binds its saved format and five-section dataset through the existing catalogue adapter.
It does not rerun the forecast engine. Re-export retains requester/scenario/entity/export
permissions and the original dataset hash. Original reports remain immutable.
The populated forecast lifecycle passes with original and catalogue reruns in JSON, CSV and
XLSX, identical data hashes and bindings, and retained source-access checks; scoped lint/types pass.

## GL zero-variance automatic certification

GL reconciliation now evaluates published AUTO_APPROVAL rules at trial-balance attachment,
using the same kind-specific matching as billing. Only a nonempty, fully stated comparison
with zero variance can qualify; absent policy or unresolved amounts retain manual review.
Both file and connector attachments share this path. Rule identity is written once (migration
0337); CTL-025, CTL-026 and the audit trail retain the comparison and certification evidence.
No policy is created or published automatically. Necessary verification covers populated file
attachment with/without policy, differences under the same policy, source-free drafts, and
existing billing certification, plus transition-migration parity and scoped lint/types.

## Secondary-book late-event reporting

New computations retain separate late-event findings for each book kept by the contracting
entity, using that book's actual posting-period resolution. Engine diagnostics and fallback
findings share book-specific identities; a primary-book diagnostic cannot suppress a secondary
finding. The out-of-period register accepts these identities and keeps its existing book,
entity, known-at and ledger-deduplication filters. Legacy findings retain their original book
scope; no historical findings or saved reports are rewritten. This does not restate historical
balance classification. Migration 0338 records the source join interpretation.

Necessary verification: two producer unit cases cover different posting periods, entity-book
membership, prior inclusion and diagnostic deduplication; a populated K07 report workflow covers
original import computation, currency views, cutoff/origin filters and separately stored IFRS15
finding visibility without ASC606 duplication. The secondary finding in that database witness
is fixture evidence, not a full second-book lock/computation lifecycle. Eight catalogue checks,
migration metadata equality and scoped lint/types pass.

## Cross-calendar revenue disaggregation

New disaggregation runs align selected whole fiscal periods by actual start/end dates. Identical
intervals combine even when local period keys differ; different or partially overlapping
intervals get separate date-labelled columns. Aligned calendars retain existing fiscal labels.
Control totals retain entity/local-period/date-to-column mappings and explain that supplied keys
select local fiscal periods. No partial-period reallocation is implied. The report can now run
across entity calendars; other reports' compatibility guards remain in place.

A retained layout marker preserves new reruns; older saved bindings keep their original fiscal
columns. Existing transaction/functional/reporting amount logic and journal comparison remain.
Migration 0339 freezes the catalogue interpretation. Necessary checks cover two interval-layout
cases, a populated mixed-calendar report compared to separate entity runs and a saved rerun,
existing journal tie-out and retained functional/reporting rate workflows, plus scoped lint/types
and migration metadata equality. These do not claim common-month allocation of 4-4-5 periods.

## Explicit cross-calendar waterfall selections

The waterfall API now accepts explicit local fiscal-key ranges across entity calendars. Its
existing retained date buckets and entity-specific amount/contributor selection supply the
required semantics: a key selects each entity's own interval, and actual dates label separate
columns. This applies to month, quarter and year; it does not force different intervals into
one common period. Legacy saved bindings retain their prior layout. Other unsupported report
kinds still reject incompatible calendars.

Necessary verification: three populated API workflows (month/quarter/year), each compared to
separate entity runs, every dated cell value checked through the explain API, and identical
retained rerun rows. The remaining calendar-guard workflow passes. Six existing date-bucket
unit cases check source separation and retained layout; scoped lint/types pass. No new financial
calculation, API schema or database migration was needed for this entry-point change.

## Period-end VC and royalty assessment controls

The final NETTING_RECLASS close pass now collects native VC reassessment and royalty coverage
facts from the engine states it already calculated, without another engine pass or changing
financial output serialization. Applicable facts become blocking CLOSE exceptions for the
selected entity/book/period, retaining subject/version or usage dates and the exact input hash.
The existing exception gate prevents lock while those findings remain open. The close run can
finish so the accountant can inspect and remedy its findings. The cockpit's VC count and
its queue link use that same period-state blocking filter, including book scope. Generated VC
findings carry the element code for the contract's reassessment banner; OPEN and IN_PROGRESS
items both remain visible. Royalty findings have a readable title. The extended lifecycle and
two focused UI workflows verify these connections; frontend type/lint checks pass.

Rechecks use stable contract-based identities, including after combination membership moves,
and settle only previously generated findings for the same book/period and assessed contracts
that are no longer present. Failed or skipped groups do not clear findings. Legacy/manual
exceptions retain existing scope. No new approval workflow is introduced.

Necessary verification: existing normal close workflow; an injected-gap end-to-end close
workflow proving persistence, book-specific gate counts and subsequent automatic settlement;
the native stage-08 reassessment and stage-09 royalty coverage cases; scoped lint/types.
The lifecycle witness injects both fact types rather than representing a full royalty contract
through the API. Existing engine limits remain: VC follows the enforced reassessment election;
royalty coverage requires a satisfied licence, accrual policy, prior covered usage and a
whole-month cadence. This does not invent an initial reporting cadence where none is recorded.

## October 23 publication and historical-backlog audit

Read against main `47db35bfc3db6de9ad624823dbca085823b31e51`:

- Approval availability is implemented, not a new development task. `_notify_assigned` sends
  APPROVAL_UNASSIGNED alerts to independently scoped access administrators; pending-request UI
  hides the warning when content is withheld. LIMITS already records B1-15 closed in its dated
  October 7 entry; its later historical C-6 table must not be treated as a new missing feature.
  This was code/evidence inspection, not a fresh approval-workflow test run.
- Close-run input freshness compares retained rate/policy signatures with the current standing
  inputs. This is distinct from historical B2-2/C-7's per-contract pinned-rate race. The latter
  was reproduced and addressed by the retained-input check described below;
  `run_inputs.standing` alone was not completion evidence for it.
- Secret-pattern scan: 4,183 tracked/nonignored files, nine allow-listed matches, zero findings
  and zero unused exceptions. It does not inspect ignored local credentials or all Git history.
- Runtime dependency licences: 142 packages (86 Python, 56 npm), eight allow-listed packages,
  zero findings and zero allow-list errors. This is a licence check, not a vulnerability audit.
- `git ls-files research-harness docs/research` returns no paths. LICENSE remains PolyForm
  Noncommercial 1.0.0; the repository is source-available under a noncommercial restriction,
  not an OSI open-source licence. No deployment or external accounting approval was attempted.

The rest of the release-candidate verification below remains outstanding; these two refreshed
checks do not certify the whole repository or replace feature-specific evidence.

## Repository completion evidence still required

After feature completion, refresh the bounded release-candidate checks recorded in PROGRESS.md
(dependency audit, local build/compose, local baseline security scan, configuration validation
and disposable restore drill). They authorize local verification, not deployment or a live
business launch. Audit remaining historical limitations against current code before treating
any as either open or complete. Registration of all report definitions alone is insufficient.

This index incorporates subsequent October 22 feature checkpoints recorded in PROGRESS.md. No independent accounting sign-off is requested
as part of this development scope.

## October 23 contract FX freshness at close — implemented

Migration 0340 retains each new computation's actual currency set and economic FX inputs.
The lock gate compares those inputs with currently committed rates through the closing date,
including contracting groups and groups with posted activity for the performing entity/book.
The close worker marks stale heads FX_REPUBLISH and uses the existing computation worker to
repair them before period-end passes. Original computations and their postings remain immutable.
Identical economic values under a new version and changes dated after the closing period do not
by themselves fail this comparison. The check conservatively covers available inputs for the
recorded currencies, not only rates individually stamped on posted lines. Legacy heads without
this evidence fail closed until a fresh computation records it; current rates are never passed
off as original historical inputs. A populated downgrade refuses to discard the new evidence.

Bounded verification: both native concurrency witnesses (approval commits after computation,
and approval published after computation cutoff) detect a clean stale head at the lock gate;
the actual close worker repairs revenue from 5,550 to 5,600 under FX_REPUBLISH and clears the
freshness mismatch. The third ordering still refuses the stale computation before posting.
The ordinary K01 close/rerun passes, as do economic-signature checks, scoped lint/types and
12 selected unit/privacy checks. Migration 0340 was applied in these populated database runs.

Two pre-existing verification gaps were surfaced and remain outstanding: the privacy catalogue
omits 11 columns (historical_source_commit, subledger_posting_commit and modification.termination),
and the offline ORM/migration comparison parser fails while reading revision 0166. The full
privacy coverage check and five dependent schema comparisons therefore do not pass. New fx_inputs
is classified and documented; these results are not a full-suite or release-candidate pass.

## October 23 privacy field catalogue reconciliation — completed

Added the two existing historical commit-evidence tables (10 identity/timing columns) and
modification.termination to the classification registry and data-model declarations. Commit
identifiers and timestamps use the existing internal-metadata rule and audit retention;
termination terms use the existing confidential-contract-terms rule. These entries do not
implement or change export authorization, deletion or retention execution. All 12 privacy
catalogue checks now pass, including complete code-column coverage and bidirectional document
agreement. This supersedes the 11-column omission reported in the preceding checkpoint.
The separate offline schema parser failure remains open; its first failure is revision 0166,
where a trailing constraint fragment is incorrectly interpreted as a column.

## October 23 migration/schema verification repair — completed

The offline migration interpreter now splits CREATE/ALTER clauses by top-level commas while
preserving nested parentheses, multiline constraints and SQL quoted text. Transactional LOCK
TABLE statements are explicitly recognized as having no column-definition effect. This fixes
the revision-0166 constraint-fragment failure and permits replay of the complete current chain.
The resulting comparison exposed documentation omissions: five composite primary keys, two
array defaults, and two nonstandard column-table headers. These declarations now match the ORM
and migration definitions; no production schema or accounting behavior changed.

All ten architecture checks and all twelve privacy catalogue checks pass. The architecture
checks include negative witnesses for type/scale, nullability and primary-key mismatches,
plus the new multiline/quoted-comma witness. This supersedes the earlier parser gap. It is an
offline definition comparison, not a new database upgrade/downgrade or full release-suite run.
