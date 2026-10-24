# Effective split history navigation — 2026-10-24

The combination split drawer now renders retained split events as an accessible table of
effective dates, destinations and original member contracts. Members sharing a destination
are grouped within each event. Standalone destinations have a readable label; member links
open the corresponding authorized contract record and close the drawer. No new destination
contract/group is fabricated, and the immutable calculation envelope is unchanged.

Entries show affected members at that event, not a reconstructed full current membership.
The existing complete-population read guard remains in place. Unknown contract identities
are displayed without fabricated links. Later split entries do not replace earlier history.

Four drawer tests, scoped ESLint and TypeScript checks pass, including historical grouping,
member navigation, incomplete authorization, preview invalidation and submission behavior.
No deployment. This completes the member-navigation entry point; foreign split layers still
await their separate allocation decision, and specialist destination calculations remain open.
