# eRev Cloud: goal and completion scope

Updated: October 26, 2026. Owner: Ray.

## Goal

Finish the eRev Cloud repository as an open-source ASC 606 / IFRS 15 revenue subledger with a usable workbench, deterministic accounting calculations, source-linked reports, and documented limitations. The repository uses **Apache License 2.0** in [LICENSE](../LICENSE), permitting commercial use, company self-hosting, modification and redistribution under its terms. This supersedes the earlier noncommercial licensing instruction.

The owner's current instructions govern scope. [Current development scope](release/CURRENT-DEVELOPMENT-SCOPE.md) records accepted accounting choices and subsequent implementation checkpoints. [PROGRESS.md](../PROGRESS.md) summarizes delivery. Earlier requirements and decision records remain design references; historical completion claims do not establish current support.

## Development priorities

- Complete remaining accounting and Reporting functionality, including original-currency and functional-currency balances, variance attribution, RPO exemptions, GL reconciliation, contract modifications and combination changes.
- Preserve original events, effective dates, recognized revenue, FX sources and replayable evidence. Unsupported calculations must remain explicit rather than display fabricated amounts.
- Finish shared-estimate application using the owner's selected rules: shared estimates override member estimates; shared breakage totals allocate by SSP and reduce effective rights quantities; prospective separation allocates remaining consideration by effective-date remaining SSP.
- Keep tenant isolation, immutable accounting evidence and key segregation-of-duties controls. Implement controls at critical accounting actions rather than building a universal approval system.
- Provide a freely editable sandbox with refresh from production. The sandbox need not reproduce production period locks.
- Prioritize feature completion and perform verification appropriate to each change. Record meaningful limitations and evidence without repeatedly running unrelated suites.

## Completion evidence

A completed capability has working engine/API/UI paths as applicable, necessary calculation and authorization checks, reproducible source evidence, and current user documentation. Accounting reports must reconcile to their underlying balances and journals. A preview is not a completed submit/apply workflow.

Before declaring the repository complete, reconcile remaining gaps in the development scope and progress records, verify the relevant integration and repository checks, and document any intentionally unsupported cases. Current deployment readiness is not implied by local verification.

## Explicit exclusions and publication rules

- No deployment, cloud provisioning, production-domain setup, or live-business operation.
- No migration-to-live-business promotion workflow. Existing import and migration capabilities may remain.
- No independent revenue-accounting sign-off as an agent delivery prerequisite.
- No complete approval-control suite or sandbox lock-history reproduction.
- No public research-harness or docs/research folders, or competitor website material in reports.
- Deliver authorized changes directly to main; do not accumulate pull requests or development branches.
- Preserve Apache License 2.0, publication exclusions, tenant safety and secrets hygiene.
