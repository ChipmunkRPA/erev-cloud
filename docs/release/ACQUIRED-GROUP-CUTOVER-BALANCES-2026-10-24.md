# Multi-member closed acquisition balances — October 24, 2026

Revision 62 extends original nonposting cutover observations to multi-member principal
acquisition groups where all members use RECOMPUTE_FROM_INCEPTION, share one cutover date
and one contracting/performing entity, and have no ordinary published balance rows. A single
original computation through the financial stages retains each member's complete transaction
balances and available functional balances. Current assets retain obligation attribution;
current liabilities use the already implemented carrying-proportional classification.

Foreign liability layers remain shared group evidence. The report reader verifies the complete
member population, member-specific original trace identities, member totals and the original
layer/current classification before returning a member amount. It never manufactures individual
FX-layer ownership. Removing a member or changing a shared member amount is refused.

The existing report population reader can now consume these complete observations. The
rollforward acquisition reader also falls back to complete member observations in transaction
currency, as it already did for foreign functional currency. Native journals, ordinary balance
population and revenue schedules remain unchanged; older evidence revisions retain their
previous behavior. Mixed ordinary/acquired acquisition-change presentation is still pending
owner choice and remains refused; agents, different cutover dates and cross-entity observations
remain outside this extension.

Validation: 59 focused acquisition, mixed-group and current-asset checks passed. An expanded
four-case native/reader check then passed across net assets/net liabilities and transaction/
foreign currencies. It exercises the real acquisition rollforward reader with database candidate
lookup and authenticated-file loading substituted; this is not an HTTP/database end-to-end test.
It checks retained report values, trace replay, incomplete populations and altered member sources.
Scoped lint/types and diff checks pass. No deployment.
