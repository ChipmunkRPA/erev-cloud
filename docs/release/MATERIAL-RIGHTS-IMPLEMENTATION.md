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
an existing missing `period_reopen_basis` builder. That separate failure is not resolved here.
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
