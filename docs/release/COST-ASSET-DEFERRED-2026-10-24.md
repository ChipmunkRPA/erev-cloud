# Foreign costs incurred before activation — 2026-10-24

Evidence revision 57 extends the existing stage-11 capitalization-on-activation rule to foreign
contract costs. The functional amount uses the applicable capitalization-date spot rate and
retains that historical basis for amortisation, acceleration and carrying. Earlier evidence
revisions keep their original refusal/output behavior. No pre-activation asset is introduced.

A native engine scenario incurs USD 10,000 before March activation, with a prior 0.9 rate and
an activation-date 0.8 rate. Capitalisation is EUR 8,000, year-end carrying EUR 4,000; asset
postings reconcile and retain the activation-rate reference. Trace replay and prior-revision
refusal are checked. Existing ordinary cost, termination rounding, missing-rate and same-currency
cases pass (6 cases), plus scoped lint/types. No deployment.

Foreign impairment, reversal and clawback measurement remain unfinished. This change does not
implement separate ERP payable settlement or a pre-activation monetary balance.
