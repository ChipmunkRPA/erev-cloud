# Foreign cost termination acceleration — 2026-10-24

Evidence revision 56 extends ordinary foreign contract-cost measurement to termination
acceleration. Cumulative regular amortisation keeps its historical carrying; acceleration
consumes the difference between total historical cost consumed and regular amortisation.
The remaining cost balance therefore reconciles exactly, including rounding residues.
JET-09e and the dated member cost balance retain the original capitalisation-rate evidence.

Native termination cases at spot rates 0.9 and 0.9000005 verify that a USD 8,400 accelerated
cost becomes EUR 7,560 and EUR 7,560.01 respectively after the already-recognised amortisation.
The second case
also proves that independently rounding the accelerated transaction amount would be wrong:
the last cent belongs to the original carrying reconciliation. Cost-asset journal net and
reported carrying are zero after termination, trace replay succeeds, and prior revision 55
continues to refuse this formerly unsupported case. Five focused cases and scoped lint/types
pass. No deployment.

Impairment, impairment reversal, clawback and delayed capitalisation remain separate foreign
cost gaps. Foreign split layer continuation still awaits the owner's allocation decision.
