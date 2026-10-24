# Ordinary current-liability currency evidence — October 24, 2026

Native evidence revision 50 publishes dated transaction-currency current contract liability
for an ordinary singleton member, linking the original stage-10 classification. It values
that current portion in functional currency from the original open liability layers using
the existing FIFO or PRO_RATA consumption policy and native cumulative rounding. Under the
ASC606 monetary override it uses the already remeasured layer carrying amounts. It does not
forecast rates, add FX entries, change revenue or reallocate total liability carrying.

The functional current node retains its classification input, original layer movement
nodes, release policy, monetary flag and per-layer current/noncurrent classification.
The existing functional balance report projector reads the dated node; the contract balance
report derives noncurrent from total less current, preserving the displayed reconciliation.
The transaction current column is retained in ordinary version balances. Functional current
is retained as dated trace evidence, not a new database amount column.

The API now produces revision 50. Older retained inputs retain the earlier behavior and
historical report bindings are not rewritten; recompute an ordinary contract to obtain the
new evidence for a newly generated report. Acquired opening-baseline members retain their
separate existing cutover path. Combination-member current allocation remains open pending
the user's choice of member allocation versus explicit unallocated group presentation.
Current contract assets and other nonzero specialist balance currency gaps are not closed
by this change. Prospective combination split persistence also remains unfinished.

Three new full-native cases pass: partial current liability with FIFO, PRO_RATA and monetary
remeasurement. The three-year EUR service example has EUR 4,000 current at March end; FIFO
values it at USD 4,350 from original 1.10/1.08 layers, while the monetary override at an
existing 1.20 closing rate yields USD 4,800. They verify report projection, trace replay and
unchanged posting intents; the historical cases also verify unchanged revenue schedules.
Existing layer classification and functional-member cases pass. The real approved-combination
API workflow passes under the new producer, including split/balance preview and no preview
writes. Scoped Ruff/mypy pass. No deployment.
