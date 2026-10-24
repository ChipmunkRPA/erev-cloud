# Foreign commission clawbacks — 2026-10-24

Evidence revision 58 adds historical functional measurement for stage-11 cost clawbacks.
The existing payee/plan and oldest-capitalisation-first transaction allocation remains in force.
Each asset supplies its own capitalization-date rate; JET-09f debits contract cost clearing and
credits the cost asset at historical carrying. This does not add reimbursement cash settlement
or ERP exchange differences. Excess recovery stays in the ERP under the existing rule.

Cumulative clawback is rounded independently of subsequent amortisation. The rounded cumulative
amortisation-plus-clawback amount less clawback determines amortisation; terminal acceleration
absorbs the remaining historical residue. Capitalisation less all releases equals carrying.
Trace inputs include the transaction clawback node and historical rate references. Old evidence
retains its prior refusal, and same-currency calculations retain existing outputs.

Necessary validation: ten native engine cases pass, including partial and excess recovery at
0.9 and 0.9000005 spot rates, every-period ledger/carrying ties, final zero carrying, trace
replay, deterministic reruns and revision-57 refusal. Scoped lint/types pass. No deployment.

Foreign cost impairment and impairment reversal remain unfinished and unsupported. No claim
of full system completion is made by this checkpoint.

## Multiple historical rates — follow-up

A further native scenario recovers USD 10,000 across two assets capitalised at 0.9 and 0.8.
The older asset is exhausted before the newer asset; each functional clawback equals its
allocated transaction amount translated at its own historical rate. JET-09f totals and both
retained rate identities agree with the trace. The targeted scenario and lint pass.

Foreign impairment implementation awaits owner selection between an independent functional
recoverability test and a clearly labelled simplified translation of transaction impairment.
The existing code tests recoverability in transaction currency and cannot silently stand in
for the independent functional test. This is a calculation-policy decision, not an external
accounting sign-off requirement.
