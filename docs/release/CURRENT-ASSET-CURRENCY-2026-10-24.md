# Dated current contract assets — October 24, 2026

Evidence revision 51 publishes ordinary member current contract assets in transaction
currency and functional currency. It covers singleton contracts and combination members;
unlike current-liability member allocation, current asset amounts follow the existing
obligation reclassification shares and their original maturity classification directly.

Stage 10 retains each eligible obligation's asset attribution under the existing twelve-month
rule (or dated zeros under NONE), with member amounts bounded by their asset totals and
reconciled to the group current asset. Stage 12 selects the same obligations' existing
functional reclass amounts, accounting for the cumulative target and prior-period target.
It does not translate the transaction current caption at an invented rate, or allocate by
a newly inferred ratio. Functional current is bounded by original member carrying. The
current inputs and source reclass nodes remain linked in the calculation trace. The report
projector reads dated amounts; the balance report derives noncurrent as total less current.

When group and contract identifiers coincide, current group trace measures are explicitly
qualified, so member current nodes remain distinct. Semantic target measures are unchanged.
The API now produces revision 51. Earlier retained inputs preserve their prior behavior;
recompute to obtain the new evidence for a new report. Acquired opening-baseline members
retain their existing separate path. Combination-member current-liability presentation still
awaits the user's allocation choice; specialist balance currency gaps and durable prospective
split application remain open.

Five new native cases pass: mixed-maturity obligations in a singleton, separate combination
members, equal group/member identifiers, disabled classification, and a mixed conditional
asset/unconditional receivable case. They verify period-specific functional projection,
member/group bounds, trace replay, and unchanged posting intents and schedules where
applicable. Together with the current-liability cases, eight targeted cases pass. The real
combination API workflow also passes under the new producer. Scoped Ruff/mypy pass.
No deployment.
