# Import reconciliation coverage — October 7, 2026

Repository audit of registered CSV v2 and legacy v1 emitters and their
`reconcile_amounts` implementations. This is a source inspection, not a full-suite
pass or an accounting sign-off. Callback presence alone does not establish complete
coverage of every field that affects accounting.

| Registered template | Current read-back scope | Remaining work identified |
| --- | --- | --- |
| contracts | Booking line prices, currencies, quantities, unit prices, out-of-scope amounts and source identity | Broader release verification |
| invoices | Signed document/line amounts, positive event amounts and tax amounts/currencies | Add invoice quantities and explicit event contract/obligation binding to the comparison |
| cost_events, pre_standard_revenue | Event amount/currency, contract, date and source identity | Add explicit obligation binding where applicable |
| usage | Rated amount/currency (including absent versus zero), contract, date and source identity | Add usage quantities and obligation binding |
| estimates | Scalar money/rates/quantities, typed parameters, scenarios, identity and element settings | Broader release verification |
| ssp_values | Entry prices/ratios, bands, currency, dimensions and value basis | Broader release verification |
| legacy_sku_ssp | Source prices/ratios, reporting currency, entries and derived bands | Broader release verification |
| legacy_contract_setup | Source-order quantities/prices, additive booking lines and linked approved VC versions | Broader release verification |
| legacy_progress_tracking | Independently aggregated billing, revenue, delivery/return events and signed invoices | Broader release verification |
| legacy_contract_modification | Signed consideration/quantity deltas, treatment, SSP reference, date/source/approval and added obligations | Scoped replay/corruption evidence in PROGRESS.md; broader release verification remains |
| progress_events | No callback | Refund amounts, quantities, progress ratios, hours and milestone weights |
| fx_rates | No callback | Currency-pair/date/rate identity and stored rates |
| bundles | No callback | Component identity and quantity per bundle |
| customers, products, gl_accounts, account_mapping | No monetary callback; reference-data emitters | Their full functional/release checks remain separate from this monetary inventory |

The unregistered CSV `modifications` template is explicitly refused by the import
API. It has no emitter; legacy modification coverage does not imply support for
that CSV template.

All enabled legacy templates now register independent readers. Financial coverage
is still incomplete for the CSV paths listed above. Some numerics are flattened as
text: an empty `amount_sums` map does not prove they were checked. Preserve source
row reconstruction, tenant/entity scope, currency and target identity, and rollback
of the entire import on disagreement when extending this gate.
