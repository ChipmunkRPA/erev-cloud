# Shared acquisition layers and report bridge — October 24, 2026

Revision 63 retains each original liability movement's contract owner in multi-member
closed-cutover observations. Report bridge source carrying now selects that owner's layers,
instead of incorrectly counting the full shared group total for every member. Original event
ownership is checked when available, together with consistent owners across each layer.
Revision 62 shared observations without owner evidence refuse this bridge explicitly; they
are not assigned invented ownership. Balance projection itself remains available.

Acquisition flow evidence also retains the complete member population. The bridge subtracts
the member presentation offset already included in the acquisition balance at the cutover
boundary. Subsequent periods use the normal change between endpoints, without a second
acquisition or spurious OTHER/reclassification. The boundary facts are retained for reruns;
old bindings without the new marker retain their prior interpretation.

Cell explanations now label the layers and current-layer amounts as group evidence and show
member carrying/current amounts separately. This avoids presenting a whole group's FX layer
as an individual member's amount. No journal, revenue schedule or FX measurement is changed.

Validation: 24 targeted acquisition-reader/layer checks passed, followed by four expanded
net-asset/net-liability and currency cases covering original source owners, acquisition-period
bridge conservation, following-period continuity and retained-input rerun equality. These call
the native engine and actual report readers/bridge with database access substituted; they do
not establish an HTTP/database workflow pass. Scoped lint/types and diff checks pass.
No deployment; pending mixed ordinary/acquired presentation policy is unchanged.

## Populated report workflow verification

The local PostgreSQL/HTTP/worker scenario now passes with two acquired contracts combined
through proposal, submission and approval. Its retained-input fixture excludes the cutover
from the computation horizon; this is not a new production lock or migration operation.
The engine produces two complete cutover observations and no ordinary cutover member rows.

Both contract balances and contract-balance rollforward succeed in transaction, functional
and reporting currency. Each member's balance, zero OTHER, rollforward balance tie-out,
shared-source explanation and source links are read through public endpoints. All six report
runs are rerun from their retained inputs: output SHA-256 and both members' explained values
and contributors match. The existing singleton foreign-cutover workflow also passes (two
populated scenarios total). Scoped lint and diff checks pass; local PostgreSQL stopped.
This supersedes the earlier HTTP/database verification limitation for this scenario only.
No deployment or overall completion claim.
