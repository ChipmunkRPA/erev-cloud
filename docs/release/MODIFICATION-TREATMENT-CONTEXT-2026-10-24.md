# Complete modification treatment context

New modification-register runs retain and render two additional text columns:
`modification_proposed_treatments` and `modification_chosen_treatments`. Each contains
canonical JSON keyed by the actual obligation identifiers in the saved modification decision.
Empty decision maps remain blank, including an unchosen draft decision.

A combined modification can name only an original member in its authored lines while the
classification and approval decision belongs to the combined host. Previously the member row
showed no treatment and the host decision was not visible. The new columns expose the entire
modification-level decision on each row, including decisions for hosts absent from the lines.
They preserve proposed/chosen differences and exact host identities without inventing a
member treatment, catch-up allocation or monetary attribution. Existing per-line columns
and monetary totals remain unchanged.

The retained `modification_treatment_maps` flag enables these columns for new runs. Older
saved runs preserve their original dataset shape and hashes. The columns apply to the ordinary
register across transaction, functional-equivalent and reporting-currency views; this change
does not alter closed snapshot evidence. The causal-analysis extension is described below.

Necessary verification: 26 focused unit cases pass, including absent chosen decisions,
proposed/chosen overrides, unchanged earlier rows/totals, old-run shape and multi-currency
context. Two populated public workflows cover PROSPECTIVE mixed unit/term changes and
CUMULATIVE_CATCH_UP cost terms through approval, application and equal-hash register replay.
Scoped type/lint and diff checks pass. No deployment.


## Causal-analysis event decisions

New causal-analysis runs also capture the exact proposed/chosen treatment maps from the
selected modification source and expose the same two columns on that event's affected-contract
rows. A combined-host decision remains keyed to its original host even when its causal effect
appears on another contract. Baseline, final, unrelated-event and unavailable rows do not
inherit a selected event's decisions. This is decision context, not a member-level amount
allocation or a change to the causal calculation.

The independent retained `modification_treatment_maps` flag preserves previous causal dataset
shapes and saved replays. A focused context witness covers proposed/chosen overrides, owner
versus affected contract, unchanged amounts/totals and empty non-event context. Public
PROSPECTIVE mixed-unit and CUMULATIVE_CATCH_UP cost-term workflows confirm preparation,
rendering and equal-hash causal replay. Scoped type/lint checks pass. No deployment.
