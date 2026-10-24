# Effective-date quantity continuation of combined components

Native evidence revision 29 accepts explicit CONTINUE assessments for in-scope combined
components using UNITS_DELIVERED or POINT_IN_TIME. Every original component remains in the
combination with positive total quantity; a reduction cannot remove already transferred units.
Only native PROSPECTIVE treatment is admitted, preserving prior recognized income and allocation
segments. The change applies at its original event position, not from inception.

The modification's retained questionnaire names its original host. For example:

```json
{
  "combined_reassessment": {
    "SERVICE": {
      "decision": "CONTINUE",
      "effective_date": "2026-01-15",
      "component_keys": ["LEASE", "SERVICE"],
      "same_transfer_pattern": true,
      "operating_lease": true,
      "nonlease_predominates": true
    }
  }
}
```

The effective date and complete original component set must match the modification/state.
Classification answers remain separate existing questionnaire members. The original lease and
nonlease products are not replaced. Added quantities resolve their original product, stratification
and SSP version label; the host's product cannot substitute. These answers are supplied assessment
facts, not criteria inferred by the engine. Existing modification authorization/approval is not
bypassed; no new public command or approval transition is introduced here.

The combined state carries each component's reassessed quantity into subsequent boundaries.
Remaining SSP uses that member quantity less its own admitted deliveries/returns and reductions.
Full subsequent termination also uses the reassessed quantity for member removal checks. Original
booking terms and prior allocation segments remain intact. Earlier evidence revisions retain their
quantity-change refusal; their successful computations keep their prior rules.

Verification: 36 native reassessment, combined-modification/termination and event-position cases
pass, plus scoped lint/types. Cases cover increases/reductions, dated complete assessments,
refusal of transferred-unit removal or retrospective treatment, later price changes, original
SSP stratification, preserved prior income and trace reevaluation.

Remaining work: term changes; complete member removal/splitting; non-unit measures; lease-predominant combinations;
combined-contract group reassessment outside this component path. No claim that the entire
reassessment feature is finished. No deployment.

## Authoring UI checkpoint

The modification wizard now offers explicit continuation confirmation for combined in-scope
unit obligations. It sends the complete original population, effective date and eligibility
facts with quantity changes. Editing the date, kind or lines clears confirmation. Reopening
the change form requires reconfirmation before saving those quantity edits. Draft saves
preserve unrelated questionnaire answers and remove stale reassessment entries.

Nineteen focused form/component cases pass, including actual checkbox submission, clearing
on date change, refusal without confirmation, unchanged price-change payloads and refusal
of term edits/removals. Frontend types and scoped lint pass. This UI checkpoint does not enable the remaining reassessment paths above.

## Public workflow and Reporting checkpoint

The populated API path now passes creation, classification, preview, submission, independent
actor approval and application for a combined original-member quantity increase. A prior
half-unit delivery keeps its 27,000.00 recognized revenue when one equipment unit and
1,000.00 consideration are added; the resulting pool is 109,000.00. Original member keys and
the complete dated assessment survive approval. Saved status and modification-register
reports replay with equal output hashes.

New modification-register runs in source/spot-equivalent currency bases include a
“Combination reassessment (authored JSON)” column with the complete retained modification-level
assessment. It is authored evidence, not a new eligibility determination or member allocation.
The column is retained-input-version gated: older report runs keep their previous shape.
Causal-analysis output and locked snapshot datasets do not gain this column in this change.

Verification: one populated public workflow including both report replays, 23 register unit
cases (including old-output compatibility and unchanged money totals), scoped lint and types.
No deployment. The term/removal/split and other measure paths listed above remain open.
