# Member current contract liability — October 24, 2026

The owner selected allocation in proportion to each member's existing liability carrying amount, with current plus noncurrent equal to each member's total. Evidence revision 54 implements that presentation rule for ordinary combinations.

Transaction current liability allocates by original transaction-currency member liability. Functional current liability first uses the original FIFO or PRO_RATA release sequence and original FX layers, then allocates by functional member carrying. Monetary overrides use existing closing carrying. Largest-remainder allocation preserves minor-unit totals deterministically; each member's share is bounded by its liability. Trace replay reads the original group-current and member-total nodes as allocation inputs. Original functional layer totals must equal member carrying totals.

The existing report projector reads the dated member nodes; noncurrent remains total minus current. No revenue schedules or journal amounts change. For supported same-currency prospective splits, each destination's separately capped current amount allocates only to its own members. NONE classification and zero-carrying members receive zero; identical group/member identifiers retain distinct source nodes.

Validation: 32 targeted acquisition/current-maturity/split tests passed. Eight current-liability cases also passed after the layer-total reconciliation guard was added. Coverage includes FIFO, PRO_RATA, monetary carrying, zero/disabled classification, report projection, trace replay, unchanged postings, and split close reconciliation. The real-database combination approval/recompute/preview workflow passed. Scoped Ruff and mypy passed.

Limits: acquired or mixed acquired/ordinary member allocations remain outside this extension. Nonzero combined current liability with inconsistent historical-versus-monetary member policies is explicitly refused. Durable prospective split submit/approve/apply and foreign destination FX continuation remain unfinished. No deployment.
