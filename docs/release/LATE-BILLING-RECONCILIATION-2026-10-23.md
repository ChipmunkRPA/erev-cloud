# Late billing reconciliation — October 23, 2026

Implemented the documented R-68(a) / CTL-024 population rule. Source invoices and contract
billing events whose origin period was locked when received now enter the first later period
open at receipt. Routing uses the entity calendar, book and historical LOCK/REOPEN/PERMANENT_LOCK
records before receipt; a later lock does not retroactively move a document. A source invoice's
first receipt across versions anchors its population so a status refresh is not a new invoice.
Normal documents remain in their original periods; billing identity and void handling remain.

The comparison and freshness checks share the same population predicates. New late events
invalidate reviewed reconciliations even where ERP billing writes no subledger line. Difference
items persist their original period in the existing origin_period_id field. The API and billing
reconciliation grid expose Origin period. New sign-off snapshots include nonempty origin IDs;
ordinary historical snapshots retain their old shape. No schema migration is required.

Necessary verification: the existing four billing-reconciliation workflows pass across targeted
runs. The lock workflow now locks January, ingests a January invoice for 123, and reconciles both
sides in February with zero difference. A later event-only invoice for 7 invalidates the reviewed
February reconciliation; regeneration exposes a -7 unmatched item with January origin through
the public API, while January remains certified. Five population/freshness unit checks pass;
two focused frontend cases cover the origin column and existing GL-risk display. Scoped lint
and types pass. These examples do not establish volume performance or every lock-history pattern.

No deployment or external accounting sign-off forms part of this change.
