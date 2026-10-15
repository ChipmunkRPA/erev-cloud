# Material-right product implementation gap

Initially traced against main 54354e5 on October 14, 2026; persistence progress updated below. This is an implementation worklist,
not evidence of completed product support or accounting acceptance.

## Current evidence

- The bundle adapter now loads persisted option terms at known_at with deterministic
  obligation keys and contract/estimate keys. Draft entry is implemented below.
- Revision 0145 now implements T-CON-14, its enum, immutable-row guards, ownership/currency
  constraints and tenant RLS. Snapshot inventory includes it and remaps its three references.
  The draft command now writes it with audited creation.
- Dedicated and embedded obligation reads now return stored terms and event-derived
  status, respecting record/effective cuts and contract visibility. Missing terms are
  still 404 on the dedicated read and null on the embedded read.
- `events/payloads.py::ContractLineV1` has no option-terms member. A separate native
  draft command creates the immutable record; correction/replacement acceptance remains open.
- `domain/migration/opening_balances.py` produces converted option records, but
  `domain/migration/capture.py::capture` explicitly refuses staging containing them.
  This refusal must remain until capture can persist and compute their actual terms.
- The eight engine regressions in `test_s03_benefit_period.py` supply `MaterialRightInput`
  directly. They verify engine behavior, not a native contract-entry path.

## Required implementation

1. Implement T-CON-14 with the specified option-type enum, tenant and obligation unique
   key, same-tenant contract/obligation/estimate foreign keys, immutable facts, RLS and
   audited creation. Enforce same-contract ownership and EXERCISE_LIKELIHOOD kind for
   the likelihood reference; money currency and ratio checks must agree with commands.
2. Define and implement option-term entry in the native contract preparation workflow.
   Entry must bind to the draft obligation and require its contracting-entity permission.
   Concurrency with activation, draft replacement and duplicate requests must preserve
   the terms approved at activation. Do not permit mutable terms to change active revenue
   without a governed event. Document the payload, transition and historical-read rules
   before adding a new public command.
3. Build deterministic MaterialRightInput records from persisted terms, with stable
   obligation and estimate keys, known-at visibility and entity isolation. Persisted
   records must agree with the event state being replayed. Do not substitute current
   terms into historical bundles or discard terms on draft replacement or regrouping.
4. Implement both the dedicated material-right read and embedded obligation response.
   Derive OPEN/EXERCISED/EXPIRED and status_date from applicable, non-voided events;
   preserve authorization and entity-scope behavior. Expose supported entry and reads
   in the workbench with errors for incomplete terms.
5. Reuse the same validated persistence path for migrated option records. Prove dry-run
   rollback and approved promotion, then remove capture's unsupported-option refusal.
   Preserve the distinction from the legacy quantity convention.

## Acceptance evidence required

- An ordinary preparer enters a draft renewal option, creates its likelihood and
  renewal-expectation estimates, and a different authorized reviewer approves them and
  activation. Read back the stored terms, compute and inspect persisted schedules,
  journals, RPO and explanation links. No direct insertion of expected output rows.
- Match the engine cases: 12,000 over 24 months at 500/month; no estimate retains the
  booked 12 months at 1,000/month; a later estimate does not reprice inception; a discount
  voucher does not inherit renewal benefit terms. Cover ASC606 and IFRS15.
- Cover entered-amount and renewal-alternative methods, exercise, expiry, event voiding,
  missing/incompatible estimates, duplicate terms, cross-contract and cross-tenant ids,
  unauthorized entities, replay at prior known_at, and activation/entry races.
- Verify upgraded and fresh databases, immutable-row protection, snapshot/restore,
  tenant export and sandbox copying. Add the table to applicable registries and schema
  manifests, not just the ORM export.
- Run the migration dry-run/promotion case with converted options and compare expected
  allocations and recognition. No bypass of approval or weakening of answer-key values.

Independent accounting review and the existing release gates remain necessary.
Nothing in this worklist authorizes deployment or external outreach.


## Persistence verification, October 14

77 focused tests passed (9.99s): database guards, tenant isolation, catalogue lint,
ORM/migration/data-model agreement and snapshot inventory/serialization checks.
The final parent-currency guard and migration round-trip tests passed (2 tests, 7.59s).
Full production typecheck passed (878 source files plus frontend); focused test/migration
Mypy and Ruff passed. Logs: `.run/material-right-schema-currency-fk.log`,
`.run/material-right-parent-guard.log`, `.run/material-right-types.log` and
`.run/material-right-focused-types.log`.

Earlier runs exposed missing snapshot pending/reference registrations and stale inventory
counts; corrected before publication. A broader row-builder completeness check also found
an existing missing `period_reopen_basis` builder. It was subsequently repaired: the
shared builder and tenant/entity-scope tests pass (10 focused PostgreSQL checks, 6.93s;
`.run/reopen-rls-verified.log`). Strict Mypy on the touched helper and isolation test passes.
Populated material-right snapshot/restore and API lifecycle acceptance are still required.


## Bundle and read verification, October 14

The adapter now passes persisted terms to real computation, including stable likelihood
estimate keys. Dedicated option reads accept `as_of` and offset-qualified `known_at`;
embedded reads use their existing context. A known event void removes its target even
from earlier effective cuts, matching engine replay. An expiry date alone does not set
EXPIRED: status derives from persisted exercise/expiry events.

Four PostgreSQL/API tests passed (22.83s), including actual material-right template
publication, stored terms entering a bundle and computation, consistent dedicated and
embedded outputs, historical absence, required timestamp offsets and foreign-tenant
isolation. The test explicitly inserts terms because the native command is unfinished;
it does not prove preparer/approver lifecycle acceptance. Route/import checks: 38 passed
(18.71s); full typecheck: 879 source files plus frontend. OpenAPI and TypeScript schemas
were regenerated. Logs: `.run/material-right-read-tests-pass.log`,
`.run/material-right-read-architecture.log`, `.run/material-right-read-types-generated.log`.

Earlier attempts exposed fixture errors: events above the stored stream head, using a
single transaction for distinct record timestamps, an uncommitted unit of work, and
query strings overwritten by the HTTP test helper's empty parameter mapping. Fixtures
were corrected without changing expected results or weakening production guards.
Native term entry, governed corrections, migration conversion and populated snapshot
acceptance remain outstanding.


## Activation approval basis, October 14

Activation approval content now binds persisted option identities and accounting fields.
No-terms contracts retain their existing content shape. A regression submitted a material-right
contract for review, inserted option terms as a fault injection without changing the event head,
and attempted approval. Before the fix approval incorrectly returned 200. Afterward it returns
409 stale-approval, leaves the contract inactive with no postings, and requires a fresh submission;
that new review successfully activates the contract.

The full activation suite passed: 19 tests in 121.46s, including ordinary routing, separate
reviewers, integration auto-approval restrictions and resubmission. Full typecheck and Ruff pass.
Evidence: `.run/material-right-approval-baseline.log`, `.run/material-right-approval-fixed.log`,
`.run/material-right-approval-regression.log`, `.run/material-right-approval-types.log`.
The baseline test failed while interpreting the unexpected 200 response as a problem body;
the request log confirms the unauthorized stale-basis acceptance, rather than an entry failure.
This strengthens the review boundary; native entry still needs group/contract locking,
permission and pending-review checks, audit, validation, and governed correction semantics.

## Native draft entry, October 14

The dedicated POST now creates terms under group/contract locks, contracting-entity permission,
parent stream precondition and a DRAFT/no-pending-review guard. It validates method inputs,
currency and likelihood ownership, computes the group and checks material-right classification,
then records AUD-FACT atomically. Invalid computations roll back creation. Generated OpenAPI
and TypeScript types include the payload and endpoint. See T-CON-14 for the command contract.

An actual API regression reproduced a separation-of-duties gap: Priya entered terms, Maya
submitted activation, and Priya could approve (200). Activation now excludes option authors
using the shared authorship reader, which also handles represented uploaders and delegation.
The regression now returns 403 self-approval, then allows Marcus to activate independently.
It also exercises missing/stale preconditions, duplicate entry, dedicated-read consistency,
and refusal during pending review and after activation. A separate test checks invalid method,
currency, likelihood and non-option classification with no retained terms or computation.

Governed corrections, replacement/concurrency acceptance, valid discount and renewal API
calculations, UI, migration conversion and populated snapshot acceptance remain outstanding.
This is not complete material-right support or accounting sign-off.

Verification: activation plus route/import/scope checks passed, 62 tests in 151.74s.
After the AUD-FACT represented-preparer lookup and replay/audit assertions, the two native
API tests passed again in 20.43s. Full typecheck (880 production files plus frontend),
Ruff and diff checks pass. Logs: `.run/material-right-native-baseline.log` (reproduced
self-approval), `.run/material-right-native-fixed.log`, `.run/material-right-native-regression.log`,
`.run/material-right-native-final.log`, `.run/material-right-native-types.log`.

## Replacement and routing, October 14

A native API regression creates terms on an integration-booked draft, lets the integration
replace its booking price while retaining the obligation key, and verifies identical term
reads and exactly one immutable record. The integration then records Step 1 and submits.
Before the routing repair its request correctly remained pending with MATERIAL_RIGHT, but
omitted MANUAL_ENTRY despite a person's term entry. This was missing routing evidence,
not a demonstrated auto-approval bypass. Activation now includes term authors and represented
preparers in MANUAL_ENTRY and persisted T-CON-14 records in MATERIAL_RIGHT. A separate
adapter fixture checks records without an option template/estimate and SYSTEM AUD-FACT
creation on a person's behalf; it is not a native migration acceptance test.

This proves price-only replacement with the same obligation key. Product/key removal,
option correction, competing commands and complete historical replacement semantics still
need their required implementation and acceptance evidence.

Routing/replacement verification: 12 tests passed in 91.18s, including the untouched-integration
auto-approval control. Represented-preparer/persisted-record fixture and import-cycle checks:
31 passed in 18.19s. Full typecheck, Ruff and diff checks passed. Logs:
`.run/material-right-replacement-baseline.log`, `.run/material-right-routing-regression.log`,
`.run/material-right-routing-facts.log`, `.run/material-right-routing-types.log`.

## Native discount calculation and expiry boundary, October 14

The preparer now enters DISCOUNT_X_LIKELIHOOD through ordinary API commands. A missing
approved likelihood pin returns 422 and retains no terms. A separate reviewer approves the
likelihood estimate, after which entry succeeds. With expected purchases of USD 100 and an
incremental discount of 0.5, rates 0.8 and 0.5 produce persisted selected SSP of 40 and 25.
The sole obligation retains its USD 12,000 allocation before and after independent activation;
revenue remains zero while unexercised. These are ASC606 regression cases, not independent
accounting acceptance or a complete relative-allocation/method matrix.

Extending the same API flow to MATERIAL_RIGHT_EXPIRED failed with 422 API-R-30: the generic
route requires a dedicated command that does not exist. Source inspection confirms that
exercise/expiry were deliberately excluded from the generic route; do not bypass that guard.
The failed attempt is retained in `.run/material-right-discount-expiry.log`.

Next lifecycle implementation must provide dedicated expiry and exercise commands with
entity permission, stream preconditions/idempotency, group/contract locks, current-option
and lifecycle validation, effective-date/evidence rules, required manual-exercise review,
audit and atomic append/compute. Expiry acceptance must prove EXPIRED/status_date, recognition
of the remaining 12,000 in this case, zero remaining allocation and balanced posted journals.
Also cover repeat/competing closure, future/effective/record cuts, partial exercise, additional
consideration/new lines and governed corrections; no direct fixture insertion may stand in for
these native commands.

Final native calculation verification: two cases passed in 31.40s; strict test-file Mypy,
Ruff and diff checks pass. `.run/material-right-discount-final.log` and
`.run/material-right-discount-types.log`. The earlier expiry attempt remains a failed
experiment documenting the missing command, not a passing lifecycle check.

## Dedicated native expiry, October 14

Implemented the dedicated expiry endpoint described in T-CON-14, with entity permission,
parent-stream preconditions, idempotency, group/contract locks, active/open/current-kind checks,
actual-expiry date bounds, optional evidence, shared posting-period validation and append/compute
audit. Synchronous computation refusals roll back; deferred work retains the established event
job behavior. Generic event append remains restricted. Exercise and reversal are still absent.

The first native run reproduced duplicate closure: a status read bounded by request time missed
a committed event stamped later by the database. Commands now check the latest committed records
under the locks; current dedicated/embedded reads use latest records when known_at is omitted.
Explicit historical cuts remain bounded. This also handles a request waiting while another
transaction commits. The historical-cut PostgreSQL regression remains in the validation scope.

Native cases cover the two approved-likelihood prices, independent activation, zero revenue before
closure, actual expiry/status date, all USD 12,000 recognized, zero remaining allocation, missing
and stale If-Match, future-date refusal, idempotent replay, duplicate refusal and one expiry event.
They also assert balanced persisted functional-currency lines and a USD 12,000 revenue credit.
Concurrency interleavings, foreign-scope expiry, declared-expiry/closed-period negative cases,
forced computation/deferred-job failures and the broader exercise/correction matrix still need
specific acceptance evidence. Do not infer complete material-right support from these cases.

Expiry verification: 56 event/obligation/read/route/import checks passed in 112.14s;
final lifecycle cases with historical reads passed in 32.49s. Full typecheck (880 production
files plus frontend), strict test Mypy and Ruff pass. Logs:
`.run/material-right-expire-regression.log`, `.run/material-right-expire-period-cuts.log`,
`.run/material-right-expire-types.log`, `.run/material-right-expire-test-types.log`.
The first historical-read assertion incorrectly treated revenue as a daily measure.
API-C-10/to_date.py instead define the containing fiscal period's end; the final test checks
that explicit measured period, daily OPEN status before expiry, and zero in the prior period.
The failed assertion is retained in `.run/material-right-expire-final.log`. The duplicate-closure
baseline is retained in `.run/material-right-expire-native.log`.

## Expiry authorization, rollback and competing requests, October 14

Added a native fixture covering DRAFT refusal, a date before the declared expiry, an auditor
without event.record, a recorder scoped to another real entity, and a recorder in another tenant.
It then injects an engine crash and compares stream head, expiry events, computations,
subledger lines, exception records and OPEN status before/after the failed command.

The baseline showed a retry defect: expiry converted a crashed computation into a cacheable
422 validation response. Writes rolled back, but the same key replayed that error after engine
recovery. FAILED now raises a server error through the command kernel, which sanitizes it and
abandons the idempotency attempt. The same request and key can then succeed; QUARANTINED
business refusals remain validation responses. No engine details are returned to the caller.

A second fixture holds the group lock, starts two expiry requests with distinct keys and the
same stream head, and observes two participant-bound PostgreSQL waiters on combination_group.
The holder can then take the contract lock, proving the waiters did not invert that order.
After release, exactly one request must succeed (201), the other must report stale head (412),
and the stream must contain one expiry and one head increment with USD 12,000 revenue.
These cases do not cover expiry versus other command types, closed-period failures or deferred
job failure/recovery; those remain acceptance work alongside exercise and reversal.

Boundary verification: both tests passed in 44.53s. Full typecheck (880 source files plus
frontend), strict test Mypy, Ruff and diff checks pass. Retry baseline:
`.run/material-right-expire-boundaries.log`; fixed outcome:
`.run/material-right-expire-boundaries-fixed.log`; types:
`.run/material-right-expire-boundary-production-types.log` and
`.run/material-right-expire-boundary-types.log`. The first fixture attempt passed a UUID
where the entity HTTP helper required a JSON string; corrected before measuring these cases.

## Populated stored-backup recovery, October 14

Native entered-amount and discount-times-likelihood options now have populated snapshot
acceptance witnesses in OPEN and EXPIRED states. The latter method includes a real approved
exercise-likelihood estimate. Each case books through commands, enters terms, independently
approves activation, optionally expires, exports a stored backup and restores it into a new
sandbox through the dispatched job. No expected result rows are inserted.

All four cases passed (42.27s): the export contains one material_right row, restore reuses
that export and leaves its manifest hash unchanged, recomputes one group with no reported
derived mismatch, preserves every terms column except tenant_id, and yields the expected
status and revenue credit (zero while OPEN, USD 12,000 when EXPIRED) in both tenants.
This verifies the populated terms and likelihood-reference load path for these ASC606 cases;
it does not establish the complete restore release gate or native IFRS15/renewal acceptance.

The shared helper's existing expiry permission, failure rollback/retry and concurrent-request
regressions also passed in the preceding run. Strict test Mypy, Ruff and diff checks pass.
Evidence: `.run/material-right-snapshot-final.log`, `.run/material-right-snapshot-fixed.log`,
and `.run/material-right-snapshot-types.log`. Initial fixture errors were a misspelled ledger
column and reuse of a globally unique sandbox code; corrected with the actual column and
separate sandbox names. No production restore behavior was changed for these checks.

## Native entry crash recovery, October 14

A fault-injection regression reproduced native entry converting an unexpected engine ValueError
into a cached 422 response. Creation now treats FAILED computations as unexpected failures:
return sanitized 500, roll back the terms/computation together and abandon the idempotency
attempt. Repeating the exact request and key after recovery creates the terms successfully;
a subsequent repeat replays that successful result without another creation audit record.

Incomplete option inputs and missing dated exercise-likelihood pins now have the specific
MaterialRightInputError subtype of ValueError. Native entry translates only that known input
failure into 422; arbitrary ValueError crashes no longer masquerade as invalid terms.
Quarantined business refusals still return 422. The regression checks unchanged contract
status/head, terms, computations, events, subledger and exception counts after failure,
then successful retry/replay and independent activation approval.

The native entry, invalid-terms and approved-discount cases plus all stage-03 tests pass:
45 tests in 62.35s. Full production/frontend typecheck, strict test Mypy, Ruff and diff checks
pass. Evidence: `.run/material-right-create-retry-baseline.log`,
`.run/material-right-create-retry-fixed.log`, `.run/material-right-create-retry-types.log`.
Other lifecycle and release requirements remain open.

## Workbench entry and expiry, October 14

Obligation Overview displays option type, SSP method, status/date, expiry date, discount
ratio and expected purchase amount, with a link to the stored likelihood estimate.
Current views offer Enter option terms on a DRAFT without terms and Record option expiry
on an ACTIVE contract's OPEN option, subject to the contracting-entity permissions.
Pending-review, completed, closed-option and historical views offer no such command.

Entry supports the three native methods and restricts renewal alternative to renewal options.
Discount-times-likelihood selects a contract/obligation-compatible estimate with a current
approved version; the API remains authoritative for its pricing-date applicability. Numeric
inputs stay decimal strings. Expiry accepts its date, reason and optional evidence uploads.
Both commands use the parent stream ETag and shared idempotency/refusal/cache handling.
Accepted expiry jobs retain progress and disable repeat submission. Failed or cancelled
computation says that expiry was recorded and requires review; it does not promise rollback.
Embedded option terms now use the same typed MaterialRightOut schema as the dedicated read.

79 UI/workbench regressions passed before the final read-only evidence link; the final
14-test option suite also passed. Backend read/API/import-cycle checks: 34 passed (27.93s).
Full typecheck (880 sources plus frontend), final frontend types, ESLint and Ruff pass.
Five local desktop/mobile form captures were generated, with discount desktop and expiry
mobile inspected for layout; no browser page errors. Evidence is in
`.run/material-right-ui-tests-final.log`, `.run/material-right-ui-tests-last-fixed.log`,
`.run/material-right-ui-api-fixed.log`, `.run/material-right-ui-full-types.log`, and
`.run/material-right-ui-visual.log`. These are isolated component and API checks, not a
complete browser-to-live-API accounting acceptance run. Governed exercise, correction,
migration conversion and the other lifecycle/release/accounting requirements remain open.

Production frontend build passed (4.25s); the existing large-chunk advisory remains.
Evidence: `.run/material-right-ui-build.log`. Local preview files/server were removed.

## Converted migration option dependency audit, October 14

The native persistence/read/UI work does not make POL-212 conversion ready to enable.
`field_mapping.map_row` changes a converted line's quantity to one and stages
`OptionRecord.option_ssp = source_quantity * source_list_price`.
`opening_balances.option_records` retains that amount with the source SSP book/version.
`capture.dry_run` still refuses every staging set containing these records before applying it.

The missing path includes the amount itself: persisted T-CON-14 and MaterialRightInput do
not carry an entered SSP amount; stage 03 ENTERED_AMOUNT obtains its point from the selected
SSP book at the booked quantity. Merely inserting T-CON-14 and removing the refusal would
therefore risk repricing a converted quantity-one option against the original catalogue
point. Several contracts can share a product/book/version while requiring different converted
option SSP amounts, so changing that shared catalogue point is not a safe general conversion.
The current source does not yet choose a per-option representation for this amount.

Before enabling capture, implement and document that per-option amount path, carry it through
bundle hashing, trace evidence, snapshot/export and promotion, and persist the immutable terms
with the same contract/obligation guards as native entry. Acceptance must include two converted
options sharing one catalogue key but having different source quantities, plus ordinary lines
using the unchanged catalogue. Assert preserved relative allocation and opening measures,
dry-run rollback, approved promotion and replay/restore. Keep the existing conversion refusal
until those witnesses pass; this audit does not close migration acceptance or accounting review.


## Explicit option SSP engine input, October 14

The engine now accepts optional `MaterialRightInput.entered_ssp_amount`: a finite,
nonnegative total in contract currency, valid only for ENTERED_AMOUNT. It is not multiplied
by quantity. Stage 03 records the amount; stage 05 uses it for relative allocation instead
of resolving the shared catalogue point as the selected amount. Catalogue metadata can still
supply account/provenance context, but the amount trace references the material-right source
record and carries its entered amount. Formula reevaluation checks that source value against
the parameter. Absent amounts retain the existing catalogue-based behavior.

The amount participates in InputBundle.sha256 when present. An absent amount is omitted only
from the input hash view, preserving the earlier shape; ordinary dataclass/evidence encoding
retains the member. Old evidence without the member decodes with None. This is not a claim
of cross-engine-version output equivalence or completion of the engine release/replay gate.

Focused acceptance includes two obligations sharing a catalogue entry with USD 25 and 75
entered amounts alongside USD 100 ordinary SSP: USD 100 consideration allocates USD 50,
12.50 and 37.50 in ASC606 and IFRS15. Separate tests cover zero, negative/nonfinite values,
incompatible method/currency, quantity-five total semantics, changed input hashes, old-hash
compatibility, old-codec decoding and input-evidence round-trip with trace reevaluation.

This is the engine dependency only. T-CON-14 storage, native command/read/UI exposure,
bundle assembly, snapshot/export and approved migration promotion still need the field.
Capture continues refusing option records. The end-to-end migration acceptance above,
release gates and independent accounting sign-off remain open.

Validation: 397 stage-03/stage-05/kernel/upgrade tests passed (29.12s); strict Mypy
passed for 880 production sources and the new test file; Ruff passed. Logs:
`.run/entered-option-engine-final.log`, `.run/entered-option-production-types.log`,
`.run/entered-option-types.log`. These witnesses do not exercise persisted native entry
or migration promotion with an explicit amount.


## Explicit option SSP storage and native workflow, October 14

Revision 0146 adds nullable immutable `entered_ssp_amount` to T-CON-14 with method and
nonnegative constraints. The money domain rejects nonfinite amounts. Existing rows keep
NULL/catalogue semantics; downgrade refuses a populated explicit amount. Native draft entry
accepts optional NonNegativeMoney only for ENTERED_AMOUNT in contract currency. Reads and
bundle assembly retain the value. Activation content includes a present amount, while an
absent value remains omitted to preserve pre-extension approval content hashes.

The workbench offers an optional total SSP field with catalogue-fallback guidance and shows
the saved amount. OpenAPI and generated types carry both command and read fields. Snapshot
inventory already copies every material-right column, so the new amount uses the same
immutable ownership, tenant isolation and reference remapping as the original terms.

Migration capture/promotion still requires implementation and retains its option refusal.
Native exercise/correction, remaining accounting witnesses and release gates remain open.

Verification: final persisted-entry/migration suite 5 passed (46.85s), including selected SSP
123.45 for quantity 50 and bound approval content. Prior native runs passed all four
snapshot/recompute cases (explicit amount or discount; open or expired), approval binding,
invalid-input rollback and bundle/API reads; failures were migration test-fixture isolation,
subsequently corrected. Schema/ORM/migration/snapshot checks: 80 passed. UI: 16 passed.
Full typecheck passed (881 sources plus frontend), strict test types, Ruff, ESLint and build
passed. Logs: `.run/entered-option-persisted-final.log`, `.run/entered-option-native-final.log`,
`.run/entered-option-native.log`, `.run/entered-option-schema-final.log`,
`.run/entered-option-ui-final.log`, `.run/entered-option-native-types.log`, and
`.run/entered-option-ui-build.log`. No browser-to-live-API release acceptance is claimed.


## Converted opening quantities, October 14

POL-212 converts the booked quantity to one option. The opening payload must use the same
unit: remaining and delivered quantities divide by the original dollar quantity; unit SSP and
remaining unit revenue rate multiply by it. Monetary balances, cumulative SSP and the immutable
source/staging rows remain unchanged. KEEP_QUANTITY_CONVENTION emits the previous values.
The transformation uses rational arithmetic and refuses a result that cannot be represented
exactly within 18 decimal places. Capture translates that refusal to its existing named Problem;
there is no silent rounding. The raw legacy rows remain available for reconciliation.

Regression first reproduced remaining quantity 10 instead of 0.4 for an original quantity 25,
and acceptance of an unrepresentable fraction. The repaired payload flows through the actual
API-to-engine payload adapter and stage-07 opening application in ASC606 and IFRS15. Witness:
quantity 25, remaining 10, delivered 15, SSP 25 and unit revenue 2.5 become one option with
remaining 0.4, delivered 0.6, unit SSP 25 and unit revenue 62.5. The opening segment preserves
remaining SSP 10, total allocation 62.5 and posted revenue baseline 37.50.

45 focused migration/capture/onboarding tests passed (1.33s); strict production Mypy passed
(881 sources), strict test Mypy and Ruff passed. Logs: `.run/option-opening-baseline.log`,
`.run/option-opening-final.log`, `.run/option-opening-types.log`, and
`.run/option-opening-test-types.log`. This is a payload and engine-boundary witness, not
capture/promotion acceptance. The option writer remains missing, capture still refuses option
records, and MIGRATION_PROMOTION remains an unimplemented approval subject. Do not remove
the refusal until immutable writes, rollback, reconciliation and approved promotion are verified.

## Shared native and migration term writer, October 14

Native entry and the migration platform applier now share `material_right_facts.insert_terms`.
The helper validates method inputs, currency, obligation ownership and likelihood ownership;
callers retain authorization, lifecycle locks, computation, audit and transaction control.
Converted POL-212 records persist their explicit total SSP before activation/computation.
Legacy records do not supply a commercial option subtype, so the writer uses OTHER and
leaves expiry/likelihood absent. KEEP rows do not create option terms. The applier buffers
contract-keyed fact audit only after successful computation and opening-evidence validation.

Database witnesses preserve total SSP 25 through the real stored-term bundle adapter, including
source decimal 25.00000000. Savepoint rollback removes both parent and option. Wrong-contract
ownership, incomplete discount inputs, negative amounts and unsupported native money precision
refuse without facts; no rounding is introduced. Five database witnesses plus existing capture
and opening-unit tests passed: 25 checks (8.09s). Native entry, failed-computation retry,
independent activation, invalid entry and both approved likelihood cases passed in the earlier
six-check run (65.49s). Logs: `.run/shared-option-writer.log` and
`.run/shared-option-writer-final.log`.

This is persistence-level evidence, not a complete converted-option import. Capture retains
its option refusal. End-to-end platform capture with real prerequisites, reconciliation and
approved MIGRATION_PROMOTION remain outstanding; the promotion subject is still missing.
The native four-decimal money boundary is also enforced for imported option terms.

## Converted option through the real platform applier, October 14

`test_converted_option_capture.py` now provisions published parity templates, an approved
LEGACY-SKU-SSP version and the entity calendar/book/state, then runs the actual platform
applier and capture reader within a savepoint. The paid product plus free option contract
has price 100 and SSPs 75/25. The converted option carries source quantity 25, remaining
quantity 10 and historical revenue 15; the native input carries one option, remaining 0.4,
explicit SSP/allocation 25 and remaining allocation 10. Contract totals remain billed 100,
recognized 15 and allocated remaining 85. Assertions also bind input hash, batch, cutover,
expected captured output, audit contract key and deletion of contract/term rows on rollback.

The integration check passed in 9.21s; strict test typing and Ruff passed. Evidence is in
`.run/converted-option-capture.log` and `.run/converted-option-capture-types.log`. Initial
fixture failures were corrected by supplying the paid line and period state; computation and
approval invariants were retained. This extends the earlier persistence-only witness through
the real engine, but does not verify the full import job or approved promotion.

Capture remains refused at its public entry. Reconciliation currently reads raw source
REMAINING_QTY in legacy dollar-units and compares it directly with the native option-unit
measure. That comparison must account explicitly for the selected POL-212 conversion without
changing retained source values or hiding genuine differences. MIGRATION_PROMOTION is still
missing. Both are prerequisites to removing the public option refusal.

## Exact conversion explanations in reconciliation, October 14

Opening-balance reconciliation now uses the verified producing bundles returned by the evidence
verifier. A POL-212 quantity explanation requires a legacy material-right row, matching contract,
obligation and product, exactly one quantity-one booking, and immutable nonlegacy ENTERED_AMOUNT
terms whose total SSP equals the source dollar-quantity in contract currency. Missing, ambiguous
or inconsistent evidence supplies no explanation. Replay mode retains its existing behavior.

The report retains both original values and the raw difference: source 10, native 0.4,
difference -9.6, outside numeric tolerance, explained by `POL-212:CONVERT_TO_OPTION_RECORD`.
The explanation uses an exact expected ratio and zero tolerance. Incorrect native quantities
refuse before comparison, including native 10 (which would otherwise look numerically equal
to source 10), missing quantities and small drift. A conflicting documented quantity explanation
also refuses. Monetary differences never receive this explanation. Source rows, retained input,
traces, report values and golden deviation files are not rewritten.

The real PostgreSQL platform-capture witness now retains its source rows and captured population
after rolling back live contracts, then runs `reconcile_batch` through the default evidence,
trace and population readers. It reaches RECONCILED with exactly one explained difference.
Two fault injections change both the captured quantity and its canonical row digest; native 10
and 0.40000001 each refuse with no reconciliation lines and status still IMPORTED. Three cases
passed (13.30s). Domain/repository/job/report/architecture checks: 93 passed (10.57s). Logs:
`.run/option-reconciliation-pg.log` and `.run/option-reconciliation-unit.log`.

This closes the demonstrated quantity-unit reconciliation gap. Public option import remains
refused until the complete import and approved promotion journey is verified. The promotion
subject is still unimplemented; independent accounting sign-off is not claimed.

## Durable promotion review basis, October 14

`jobs.assess_batch` now supplies the same read-only evidence/trace/source assessment to
reconciliation and the new `promotion_review.review_basis`. The review refuses before
RECONCILED (and outside opening-balance mode), rechecks every figure and explanation, requires
no unexplained difference, and compares the entire stored line set with that assessment.
Missing, duplicate or altered lines cannot pass by relying on the batch's status. Retained
legacy rows must also match their original row hashes.

The basis binds the source file/hash, cutover, capture operation, full stored source rows,
verified captures, reconciliation rows, profile (including replayed SSP references), registry
and reconciliation/report identities, and control totals. Approval linkage, lifecycle status
and batch update timestamps are excluded: moving RECONCILED to SUBMITTED keeps the fingerprint,
while a changed SSP profile changes it. It writes no facts, audit events or live contracts.
The eventual submit/decision caller must hold its lifecycle lock while checking this basis.

The actual PostgreSQL capture/reconcile witness exercises repeated stable reads, refusal before
reconciliation, four malformed stored line sets, status stability and changed-profile binding.
Three cases passed (9.56s), and 68 related job/repository/architecture/domain checks passed
(9.20s). Strict production typing (885 sources), the test file and Ruff passed. Logs:
`.run/migration-promotion-review-pg.log`, `.run/migration-promotion-review-unit.log`,
`.run/migration-promotion-review-types.log` and `.run/migration-promotion-review-test-types.log`.

This is the durable evidence portion of promotion, not the complete approval subject. It does
not yet validate current configuration or report execution, publish the legacy policy preset,
reproduce and compare approved contracts, enforce activation admission, or atomically create
live contracts. The subject, route, independent approver/MFA journey and public option import
remain unavailable until those pieces are implemented and verified together.

## Confirmed opening plan and input reconstruction, October 14

Successful opening-balance imports now retain a versioned `profile.opening_plan`: the complete
normalized batch parameters, confirmed entity mapping, staging digest and plan digest. The plan
covers staged booking lines, exact opening balances and option records. Restoring it uses the
retained source rows and cutover; absent/unsupported plans, incomplete parameters, malformed
representations, invalid hashes or changed staged facts refuse by name. Older captures without
this plan need re-import before promotion; no choice is inferred from current defaults.

Promotion review restores this plan and compares its booking and opening payloads against the
verified producing input, requires the complete captured contract population and migration
customer identity, and compares every immutable option term. Numeric option values compare
exactly: database 25.0000 and source 25 are equal without rounding or discarding other fields.
This comparison is separate from the plan hash; a self-consistent newly hashed plan that changes
KEEP/CONVERT or entity mapping still fails against the original capture.

The registered import worker with a non-identity entity mapping stores a reconstructable plan
for all four fixture contracts (1 check, 12.72s). The converted-option database witness includes
missing-plan and freshly hashed changed-choice refusals: 3 cases passed (12.10s). Event dates
and MIGRATION origin are also bound. Strict production typing (886 sources), two test files,
the final plan helper and Ruff pass. Domain/import/reconciliation and
architecture checks: 70 passed (9.96s). Logs: `.run/migration-opening-plan-import.log`,
`.run/migration-opening-plan-pg.log` and `.run/migration-opening-plan-unit.log`.

This provides confirmed-input reconstruction for the future promotion writer. It does not yet
recompute and compare outputs under current configuration, publish the legacy preset, enforce
activation admission or create live contracts under independent approval. Public converted-option
import and the promotion route remain unavailable; no production readiness or accounting sign-off
is claimed.

## Complete opening output reproduction, October 14

Promotion review now replays each verified retained input with the current engine and requires
its complete output hash to equal the captured hash. It restores the confirmed plan, rebooks
through the real platform applier under current configuration inside a child savepoint, and
compares the entire OutputBundle except its input hash. Fresh identities/observation time
change that input hash; engine version, every book and trace, schedules, posting intents,
proposals, triggers and diagnostics remain in the comparison. No reconciliation-only projection
or tolerance replaces this exact comparison. The review basis is version 2 and includes the
per-contract result hashes. All temporary rows and child audit buffers are discarded on either
success or failure.

The converted-option PostgreSQL witness checks a later observation time, bad retained output
hash, missing current product template, changed diagnostics outside the reconciliation figures,
enabling IFRS15 after capture, and rollback: 3 cases passed (12.78s). Related domain, job,
repository and architecture checks: 126 passed (17.23s).
Strict production typing passed for 887 sources. Logs: `.run/migration-reproduction-*.log`.

This is preflight only. Policy publication, report validation, activation admission, configuration
locking through approval/live creation, independent reviewer/MFA and the public promotion route
still need implementation. Converted-option import remains guarded. During negative testing,
changing a product to AGENT without a reviewed PRINCIPAL_AGENT record exposed a raw ValueError
from stage 03; the following entry records its typed error-handling correction. No deployment
or production/accounting sign-off is claimed.

## Principal-agent reproduction input refusal, October 14

Missing reviewed principal-agent records, unsupported gross-to-net bases, absent rate/amount
members and malformed exact numbers now raise PrincipalAgentInputError (a ValueError subclass
preserving CV-45). Migration capture returns a named 422 validation problem for these known
input failures; retained/fresh replay also reports a named refusal. Gross-to-net arithmetic and
S03-INV-05 range invariants remain unchanged. Unexpected engine ValueErrors still propagate;
they are not relabelled as correctable user inputs.

The real converted-option reproduction witness changes the current product to AGENT without
a review, asserts 422, and verifies rollback of contracts, option terms and child audit events.
A separate injected unexpected ValueError also rolls back and remains unexpected; the original
review basis still reproduces afterward. Specialist/agent-billing/capture checks: 46 passed
(16.49s); final PostgreSQL/architecture checks: 66 passed (31.00s), including the added unexpected
failure regression. These runs overlap in three database cases. Production plus database-test
strict typing passes (888 sources), and Ruff passes. Direct strict checking of the older
specialist test file reports 28 unchanged helper typing diagnostics; the same errors reproduce
from the prior committed file. Evidence: `.run/agent-input-refusal-*.log` and
`.run/agent-specialist-baseline-types.log`. This does not implement principal-agent review entry,
promotion approval, activation admission, or accounting sign-off.

## Activation prerequisites and pending reviews, October 14

The review basis is now version 3: each reproduced contract carries its result hash and the
complete checklist from the fresh pre-activation event. Missing, duplicate, foreign-contract,
incomplete or malformed checklist evidence is refused. Failed mandatory fields, source reference,
product/template/SSP, combination suggestions or existing judgement records refuse with the
normal activation-checklist problem and rule codes. An inactive current product can reproduce
the accounting figures but now fails this prerequisite check; the database witness verifies it.

BS3-D-23/26 require the future promotion approver to review the distinctness and collectibility
records. Their failed checks remain false and are listed in pending_review_checks, with
ready_for_activation false. This is review preparation, not an activation waiver or a claim
that those judgement records already exist. The future writer must create/review the records
under the fresh approved basis and enforce every checklist item before persisting activation.

The three PostgreSQL cases passed (17.78s); 101 related domain/capture/architecture checks passed
(17.04s), including each non-review blocker and ambiguous/missing checklist evidence. Strict
production plus both changed test files passes (890 sources); Ruff passes. Logs:
`.run/migration-activation-review-{pg,unit,types}.log`. The public promotion route and converted
option import remain unavailable; independent approval, policy/report checks, atomic live
creation, current release verification and accounting sign-off are still outstanding.
