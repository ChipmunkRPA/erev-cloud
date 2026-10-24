# Functional sources in cost rollforwards — 2026-10-24

The cost rollforward previously selected transaction amounts even for its default functional
view. Foreign transactions were consequently refused by the currency guard despite native
functional cost postings being available. New functional/reporting runs now select the actual
posted functional amount and currency. Closing carrying is projected from the retained native
functional cost targets, with locked-period source selection, before the cost tie-out and
reporting-currency translation. There is no conversion of transaction captions at a new rate.

The retained `cost_functional_sources_v1` marker preserves this source choice for reruns.
Older bindings without the marker keep their original reader and refusal behaviour; transaction
views retain their original amounts and currency separation. The existing reporting-currency
translation continues to show monthly FX and rounding separately.

Validation: 15 targeted source-selection, rollforward and translation checks, including old
bindings and the functional carrying tie-out; one real-database cost-report workflow; scoped
lint/types. Earlier native cost tests verify the historical carrying used by this reader.
No deployment. Engine gaps for impairment/reversal/clawback/delayed capitalisation remain;
this report change does not fabricate functional amounts for unsupported computations.
