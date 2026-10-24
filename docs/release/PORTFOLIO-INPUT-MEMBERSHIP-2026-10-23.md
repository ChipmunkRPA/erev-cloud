# Portfolio memberships in calculation inputs — October 23, 2026

The API bundle builder now supplies its group's portfolio memberships instead of always
writing an empty portfolio list. Membership is selected at the computation's record-time
cutoff: the join is inclusive and the removal is exclusive. Removed and rejoined membership
rows retain their earlier intervals. Member keys and portfolio keys are deduplicated and
sorted for canonical input hashing. The native portfolio code is the immutable portfolio ID,
so changing a display code does not rename a source in historical calculations.

The snapshot includes only contracts of this computation group. It is not the full cross-group
population for SSP allocation. This is record-time membership, not an effective-date membership
or a frozen approved application. Shared estimate versions still require the application loader,
member targets and approval/event integration before the public workflow affects revenue.

The public portfolio workflow verifies snapshots before joining, at joining, at removal,
and after rejoining, and verifies that the actual bundle builder carries the snapshot.
Scoped Ruff and mypy pass. No deployment or approval activation.
