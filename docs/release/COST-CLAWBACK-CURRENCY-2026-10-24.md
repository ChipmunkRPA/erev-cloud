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
