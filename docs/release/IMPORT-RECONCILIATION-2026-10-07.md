# Import reconciliation coverage — October 7, 2026

Repository audit of registered CSV v2 and legacy v1 emitters and their
`reconcile_amounts` implementations. This is a source inspection, not a full-suite
pass or an accounting sign-off. Callback presence alone does not establish complete
coverage of every field that affects accounting.

| Registered template | Current read-back scope | Remaining work identified |
| --- | --- | --- |
| contracts | Booking line prices, currencies, quantities, unit prices, out-of-scope amounts and source identity | Broader release verification |
| invoices | Signed document/line amounts, positive event amounts, taxes, quantities at database precision, contract/obligation/product identity, dates, invoice links and tax classifications | Broader release verification |
| cost_events, pre_standard_revenue | Event amount/currency, contract, obligation, date and source identity; cost purpose/flags/payee/plan | Broader release verification |
| usage | Rated amount/currency (including absent versus zero), quantity, obligation, usage period/metric, contract, date and source identity | Broader release verification |
| estimates | Scalar money/rates/quantities, typed parameters, scenarios, identity and element settings | Broader release verification |
| ssp_values | Entry prices/ratios, bands, currency, dimensions and value basis | Broader release verification |
| legacy_sku_ssp | Source prices/ratios, reporting currency, entries and derived bands | Broader release verification |
| legacy_contract_setup | Source-order quantities/prices, additive booking lines and linked approved VC versions | Broader release verification |
| legacy_progress_tracking | Independently aggregated billing, revenue, delivery/return events and signed invoices | Broader release verification |
| legacy_contract_modification | Signed consideration/quantity deltas, treatment, SSP reference, date/source/approval and added obligations | Scoped replay/corruption evidence in PROGRESS.md; broader release verification remains |
| progress_events | Refund amounts/currency, quantity, progress ratio, hours, milestone weight/code, obligation, trigger/measure, contract, date and source identity | Scoped tests in PROGRESS.md; broader release verification remains |
| fx_rates | Submitted version/set/coverage/upload identity, all entered rates and derived inverses at 12 places, pair/type/day/period identity and per-source targets | Broader release verification |
| bundles | Complete replacement, per-source target identity, component quantities/split ratios at database precision, sequence and effective windows (including derived end dates) | Broader release verification |
| customers, products, gl_accounts, account_mapping | No monetary callback; reference-data emitters | Their full functional/release checks remain separate from this monetary inventory |

The unregistered CSV `modifications` template is explicitly refused by the import
API. It has no emitter; legacy modification coverage does not imply support for
that CSV template.

All listed financial CSV templates and enabled legacy templates now register independent
readers with the scopes above. This does not establish full accounting or release coverage.
Reference-data workflows still require their separate checks. Some numerics are flattened as
text: an empty `amount_sums` map does not prove they were checked. Preserve source
row reconstruction, tenant/entity scope, currency and target identity, and rollback
of the entire import on disagreement when extending this gate.
