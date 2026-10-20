# Retained revenue source classes — October 20, 2026

Posting role targets now retain `input_classes` in the same order as their signed inputs,
and `time_functional` in functional minor units. Uniform part contributions are classified
TIME or EVENT from both original currency amounts. A part containing both classes is
explicitly marked MIXED; its owners are not inferred by proportional allocation.

Revenue attribution reads those retained classifications for each original revenue input.
It projects that input's original signed functional layers and checks the summed TIME
amount in both transaction and functional currency against the original target. This
supports aggregations of separately classified sources, including negative event amounts
that reduce a positive TIME target, without assigning one class to the whole net amount.
Prior targets and paid history continue through the existing signed delta reconciliation.

Older traces without input classes retain their uniform-target behavior. A mixed legacy
target, a malformed class list, or a new internally mixed input is refused. Split-role
inputs and non-revenue component sources remain subject to existing attribution limits.
This change does not complete all mixed TIME/EVENT public workflows or accounting acceptance.

Necessary verification:

- 31 tests passed across the posting delta and revenue trace modules, including an engine
  target with TIME 100 / EVENT -40 transaction and TIME 80 / EVENT -36 functional amounts.
  The target retains the two original input references and distinct classes.
- The database test `test_intercompany_due_to_sources_support_progress_reversal` passed,
  exercising actual computation, transaction/functional/reporting views and retained reruns.
  This verifies compatibility of the new metadata with that public workflow; it is not an
  end-to-end mixed-input accounting acceptance test.
- Ruff and targeted mypy passed. No deployment was performed.
