# Material-right product implementation gap

Initially traced against main 54354e5 on October 14, 2026; persistence progress updated below. This is an implementation worklist,
not evidence of completed product support or accounting acceptance.

## Current evidence

- `backend/erev_api/domain/contracts/bundles.py::_header` unconditionally sets
  `ContractInput.material_rights=()`. Native computations therefore never receive option
  terms, including the renewal option needed to reach POL-029.
- Revision 0145 now implements T-CON-14, its enum, immutable-row guards, ownership/currency
  constraints and tenant RLS. Snapshot inventory includes it and remaps its three references.
  There is still no native command that writes it.
- `domain/contracts/obligations.py::material_right_out` checks obligation visibility and
  then always raises not-found. `queries.py` also emits `material_right=None`.
- `events/payloads.py::ContractLineV1` has no option-terms member. There is no native
  command to persist the missing record.
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
