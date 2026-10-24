# Acquired POB opening baselines — October 23, 2026

Native transaction-currency FIFO_WITHIN_POB now starts post-acquisition eligibility from the
original cutover billed/revenue baseline. Previously it excluded pre-acquisition flows without
restoring that baseline, classifying qualifying subsequent revenue as other increases instead
of revenue from opening liability.

The acquisition period still reports the established balances as BUSINESS_COMBINATIONS, with
no period-opening liability. Later periods add post-cutover billing and signed revenue to the
original baseline. Pre-cutover invoices are not counted again. Authenticated frozen obligation
openings retain priority over reconstructed baselines.

Native closing snapshots now retain each acquired obligation's billed amount, cumulative
revenue, liability eligibility and original baseline trace ID in transaction currency. These
are eligibility amounts before the group cap, not allocations of the group's final liability.
Missing, mixed-date or non-cutover-method baselines are not silently substituted. Functional
acquisition snapshots still require original foreign-currency baseline evidence and remain
unavailable through this new path.

Evidence revision 14 enables the behavior for newly built API bundles. Revision 13 and earlier
retain their original output/admission behavior. Journal amounts and recognition timing do not
change.

## Verification and boundary

37 focused cases pass, including six complete engine comparisons across ASC606 and IFRS15,
acquisition/current/subsequent periods, and presence/absence of pre-acquisition invoices.
The acquisition period is open in these fixtures. Outputs retain the original baseline and
post-cutover sources, group closings reconcile, and posting intents equal revision 13.
The frozen-opening guard, existing native snapshot/union cases and scoped lint/types pass.

This completes the native transaction baseline correction and closing-source capture, not the
entire acquired Reporting feature. Foreign-functional source amounts, recompute-from-inception
baselines, public acquired-report workflows and broader acquired locked histories still need
implementation or verification. The exact closed-cutover missing group closing is subsequently
fixed in [revision 15](ACQUIRED-CLOSED-CUTOVER-2026-10-23.md); broader acquired histories remain
open. No migration-to-live or deployment work is included.
