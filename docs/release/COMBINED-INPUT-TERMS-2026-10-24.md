# Combined cost/hour common-term continuation

Evidence revision 32 admits complete common-end-date TERM_CHANGE for in-scope COST_TO_COST
and LABOUR_HOURS combinations. Every original member must have one CHANGE line, zero
quantity delta, unchanged start date and the same end date on or after the effective date.
The original dated CONTINUE assessment and all eligibility confirmations remain required.

The wizard now offers term confirmation for these methods while keeping quantity continuation
restricted to unit methods. Existing classification and approval controls determine treatment.
For cost/hour term changes the application accepts native CUMULATIVE_CATCH_UP as well as
PROSPECTIVE; it does not force a prospective override of the classifier. Unit/time continuation
keeps its previous prospective-only rule. The existing native cost/hour boundary reads scoped
EAC and original cumulative inputs; delivery counters cannot substitute for those measures.

Verification:
- 21 native reassessment cases pass. Cost/hour tests cover both treatments, retained 30%
  progress at the boundary, later original-member inputs taking progress to 40%, unchanged
  pre-change January schedules, exact trace reevaluation and refusal under revision 31.
- Two populated public workflows use approved combination-wide EAC and explicitly scoped
  member costs/hours. Both classify to CUMULATIVE_CATCH_UP, preview, approve and apply.
  The 108,000 allocation keeps 32,400 income for unchanged 30% progress; status, modification
  register and causal-analysis reports replay with identical output hashes.
- Scoped backend/frontend types and lint pass.

COST_RECOVERY still lacks native modification-boundary measurement and remains refused.
OUTPUT_PERCENT/MILESTONE combination scope is still awaiting the owner's decision.
Divergent member terms, changed starts, simultaneous quantity/term changes, partial removal,
splitting and combined-contract group reassessment remain unfinished. No deployment.
