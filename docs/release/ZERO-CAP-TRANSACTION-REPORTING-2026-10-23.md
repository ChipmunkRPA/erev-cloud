# Transaction-currency special-contract zero-cap reporting

The FIFO_WITHIN_POB reader now admits agent and cross-entity-performer contracting-entity
rows in transaction currency when the reconciled group opening is nonpositive, or when
net consumption is nonpositive and the caller allows the zero-consumption shortcut. The
functional/reporting path already supported these cases; the transaction reader unnecessarily
required unsupported special-source attribution despite the mathematically zero relief cap.

The report retains signed actual revenue, posted line identities, cap values and explicit
ZERO_GROUP_OPENING or ZERO_CONSUMPTION evidence. Unknown obligation subjects, missing line
identities and missing retained obligation populations still refuse. Original locked-source
authentication stays upstream. Positive opening plus positive consumption still requires the
unfinished special-source attribution; no agent gross amount becomes net revenue. Existing
principal transaction evidence shape is unchanged. Reporting ranges can still disable the
zero-consumption shortcut when earlier positive relief and later reversals have different FX.

Necessary validation: 34 focused POB, frozen-source and retained-cell cases pass. The special
cases cover both transaction and functional views, agent and cross-entity performers, zero and
negative net consumption, actual signed revenue, unknown-subject refusal, positive-cap refusal
and the reporting-range override. Scoped types/lint and diff checks pass. No populated public
report workflow was rerun for this reader change. No posting changes, migration or deployment.
