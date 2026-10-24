# Effective split netting and close reclassification — October 24, 2026

Evidence revision 53 integrates retained prospective split membership into the ordinary engine's period-end presentation. Supported same-currency fixed-service obligations now net only within their effective destination. The original calculation envelope remains available for historical allocation and event lineage; its displayed totals sum the destinations without offsetting their assets against other destinations' liabilities.

Obligation reclass amounts feed the existing NETTING_RECLASS close pass and next-period reversal. Pre-split balances and posting intents remain unchanged, as do income schedules and revenue-recognition intents. Current liability is capped within each destination before the envelope's current amounts are summed. Current assets retain obligation maturity attribution.

This is native calculation and close support, not a completed public application workflow. Persisted effective membership, submit/approve/apply integration and official destination-history navigation remain open. Foreign destination posting and specialist/opening continuation are explicitly unsupported; the independent transaction-currency preview remains available without pretending to carry historical FX layers.

Validation: 29 targeted split/current-maturity tests passed, including successive splits, billing before or after separation, unchanged pre-split history, independent destination/member balance agreement, full trace replay and repeatability. For September through November, command plus close-pass journal totals reconcile to CL, CA and unbilled balances. Scoped Ruff and mypy passed. The existing real-database combination workflow was also checked separately.

Owner decision received during this work: allocate group current contract liability to members in proportion to their existing liability carrying amounts, with each member's current plus noncurrent equal to total. This resolves the policy question; member allocation implementation remains the next separate change. No deployment.
