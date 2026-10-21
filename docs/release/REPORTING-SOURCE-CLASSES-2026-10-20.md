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

Older traces without input classes retain their uniform-target behavior. Mixed legacy targets
and malformed class lists remain unsupported. New role targets additionally retain signed
`input_time_txn` and `input_time_functional` minor-unit amounts per input when the original
part has one signed input. Multi-input parts explicitly retain `unresolved`, not a ratio.

An internally mixed input with those exact amounts can now split TIME and EVENT when all its
original revenue sources have the same contract, layer, movement kind, effective date and
source key. Both currency totals still reconcile to original target evidence; prior targets
and paid history retain their existing reconciliation. This preserves S14's functional TIME
amount rather than introducing a new report-side FX or allocation rule. Multiple original
provenances can additionally use the period-class path described below. Split-role inputs and non-revenue component sources retain
their existing limits. Full mixed-workflow/API acceptance and independent accounting sign-off
remain open.

Additional scoped checks cover the retained negative input amounts, signed and zero-net
splits, and refusal of different contracts, layers or source keys. These checks do not prove
that every mixed multi-layer scenario can be decomposed.

Necessary verification:

- 31 tests passed across the posting delta and revenue trace modules, including an engine
  target with TIME 100 / EVENT -40 transaction and TIME 80 / EVENT -36 functional amounts.
  The target retains the two original input references and distinct classes.
- The database test `test_intercompany_due_to_sources_support_progress_reversal` passed,
  exercising actual computation, transaction/functional/reporting views and retained reruns.
  This verifies compatibility of the new metadata with that public workflow; it is not an
  end-to-end mixed-input accounting acceptance test.
- Ruff and targeted mypy passed. No deployment was performed.


Recognition-period source attribution now supports multiple original owners/layers across
separately classified periods. S14 retains `input_period_classes`, aligned to its signed inputs,
from original relief causes through the target period: NORMAL is TIME only for obligations
released at close; other causes are EVENT. A period containing both stays MIXED. Concession
components and unresolved multiple-input/split shares do not claim period evidence.

The report matches each original S12 source key to the exact input subject and retained period,
keeps its signed source amount and ownership, and verifies TIME totals independently in both
currencies. This enables mixed cumulative inputs without proportional source allocation. A
within-period mixture, missing classification or functional TIME mismatch remains unsupported.
The single-provenance path and legacy behavior are preserved. Focused cases exercise opposite
signs, distinct owners/layers, reversal coefficients and both currency views; the original
engine example verifies TIME/MIXED/EVENT period metadata and historical cutoff. Existing DB
intercompany reversal compatibility passes; full public multi-period mixed acceptance remains
open. Migration 0220 records this scope. No deployment.


Split-role reader foundation: the original role-target formula can now be replayed in both
currencies for one uniquely owned revenue input. Retained weights, role index, side sign and
minor-unit rounding must reproduce the original transaction and functional role amounts.
TIME/EVENT amounts reconcile to the retained role classification, and source ownership is
preserved. Multiple origins and non-revenue inputs remain unavailable.

This is not complete agent reporting: `revenue_attribution.for_control` still requires a
one-to-one revenue/control counterpart. Agent gross control relief also includes the supplier
leg, and the current close-pass revenue paid population contains REVENUE and INTERCOMPANY_DUE_TO,
not AP_SUPPLIER. The next integration must retain/verify that supplier history and distinguish
net revenue from gross control relief without relaxing entry reconciliation. No public agent
report acceptance is claimed by the scoped formula checks.
