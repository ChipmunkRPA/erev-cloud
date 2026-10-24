# Foreign acquisition original balances — October 24, 2026

Revision 45 extends the original nonposting acquisition observation to a singleton
principal contract whose transaction currency differs from its functional currency.
Its supplementary pass runs through the original FX stage with the original rates,
policies and calendar states. It never runs posting. Functional member balances are
cross-checked with the ordinary layer-to-balance projection before capture, and all
sources remain in the separate trace namespace.

The snapshot retains transaction balances plus the functional measures actually
published by stage 12, each with its currency, precision and original node. The
report reader verifies those nodes and scope before admitting the transaction
balance row. This unlocks transaction-currency contract balances and rollforward
for that no-ordinary-row population. Cell explanations show the original functional
amounts and clickable calculation sources alongside transaction amounts; saved
reruns retain both source sets.

This does not complete functional or reporting-currency views of this population.
Functional current/noncurrent classification is not invented from a display FX
rate. The owner has been asked whether current liability should consume the original
historical layers in the existing relief order or use the transaction-current ratio
of total functional carrying. That choice remains pending. Other unsupported
functional measures and multi-member/agent acquisition paths remain open.

Validation: the acquisition public scenario file passes ten cases, including the
new foreign case. After adding the layer-to-target cross-check, the focused foreign
case passes again and explicitly verifies EUR 20,000 transaction liability and USD
22,000 original functional liability at historical 1.10, rather than USD 22,100 at
closing 1.105. It covers original functional source links, transaction reports,
rollforward reconciliation, before-cutover exclusion, later-period carry, and saved
balance explanation reproduction. Scoped Ruff/mypy and diff checks pass.
No deployment or overall completion claim.
