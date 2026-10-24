# Recomputed member current liability — October 24, 2026

Evidence revision 60 extends the existing carrying-proportional member allocation to principal
business-combination contracts using RECOMPUTE_FROM_INCEPTION. It handles mixed onboarding
methods and entirely recomputed groups using actual computed member balances, not imported
opening amounts as a substitute. Transaction nodes feed the existing balance output; functional
nodes use the same original-layer classification and carrying reconciliation as other members.

Single-member closed-cutover observations already retained functional current liability since
revision 47. The new member path now reuses its original node when the independent layer
classification agrees; a discrepancy fails explicitly. The original layer evidence and report
adapter remain available, without duplicate trace identifiers. This is not a new permission to
post foreign recomputed onboarding differences: the existing stage 14 refusal remains intact.
Acquired agents and non-acquisition openings remain excluded.

Validation: 50 focused acquisition/current-liability cases pass, including two new continuing
combination cases and four closed-cutover cases across currencies and FIFO/PRO_RATA. The latter
verify a 180,000 transaction liability with 120,000 current; at the original 0.8 rate, functional
amounts are 144,000 and 96,000 despite a 0.9 closing rate. Report evidence reads back unchanged;
trace replay, proportional member amounts, unchanged journals/schedules and the closed-cutover
absence of ordinary balances are checked. Scoped lint/types and diff checks pass.
No deployment; older input revisions keep their existing interpretation.
