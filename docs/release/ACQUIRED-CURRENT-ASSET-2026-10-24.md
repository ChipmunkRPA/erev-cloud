# Acquired cutover functional current assets — October 24, 2026

Evidence revision 52 retains functional current contract assets in original nonposting acquisition observations. Scope is the existing single-member, same-entity principal business combination using RECOMPUTE_FROM_INCEPTION with an otherwise unmeasured closed cutover. The original group current classification belongs to that sole member; original obligation functional reclassification shares determine its carrying amount. Noncurrent remains total minus current.

This extends the existing authenticated report snapshot and its trace, not journal posting or income scheduling. Revision 51 and earlier remain unchanged. Conditional and unconditional rights remain separate. A mixed-maturity example has USD 100,000 total assets and USD 20,000 current; at the original EUR 0.9 closing rate, EUR 90,000 total and EUR 18,000 current leave EUR 72,000 noncurrent.

Validation: 17 focused tests across acquisition cutover/report-adapter and ordinary member current assets passed; trace replay, prior-version journal/schedule/balance equality, conditional/unconditional rights, and mixed maturity were checked. Scoped Ruff and mypy passed.

Remaining limits: mixed acquired/ordinary groups, specialist foreign cost/return/loss measurements, and combination-member current liability allocation remain separate work. Prospective combination split submission/application is still unfinished. No deployment or live-business migration was performed.

The goal document now reflects the owner's current publication and development scope. PolyForm Noncommercial remains the license; historical MIT wording does not govern this repository.
