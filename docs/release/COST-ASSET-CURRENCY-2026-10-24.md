# Ordinary contract-cost currency — 2026-10-24

Evidence revision 55 supplies functional capitalisation, cumulative amortisation and carrying
for ordinary foreign-currency contract cost assets. The pinned capitalisation-date spot rate
sets historical carrying. Cumulative amortisation consumes that carrying proportionally;
remaining carrying is capitalisation less amortisation, including the final rounding residue.
The native JET-09 posting targets retain the original rate references. Reporting reads dated
member carrying nodes, summing only complete asset populations, rather than applying a closing
rate to the transaction balance. Same-currency outputs remain unchanged.

Scope: cost occurrence and capitalisation share a date, with ordinary amortisation and no
nonzero impairment, reversal, clawback or termination acceleration. Other foreign cost cases
still require native measurement and are refused. Return assets and loss provisions remain
separate gaps. Foreign combination split layer distribution still awaits the owner's choice.

Necessary verification: 12 focused native cost/current-liability checks, plus a final three-case
cost check including same-currency compatibility. A USD 10,000 cost at 0.9 retains EUR 4,500
after one year despite a 1.2 closing rate; posted cost-asset net and report carrying reconcile,
rate references survive, the terminal balance is zero, and trace replay/rerun agree. Missing
FX rates report their original blocking finding instead of an unrelated layer-classification
error. Scoped Python lint/types pass. No deployment; whole-repository completion is not claimed.
