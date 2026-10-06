"""Legacy migration (BUILD_SPEC LMG-1 to LMG-4; 04 T-MIG-01 to T-MIG-03, §17; ENGINE_SPEC §7.4
S07-R-11, S07-R-12; D-31 modes (a) opening balances and (b) replay).

Pure modules, in dependency order: ``legacy_db`` (the one ``sqlite3`` reader of ``erev_api``,
DG-LAY-11, read-only immutable copies), ``field_mapping`` (04 §17.2 legacy → eRev, POL-211 to
POL-214), ``opening_balances`` (S07-R-11 staging and the S07-R-03 consistency check),
``reconciliation`` (T-MIG-03 lines, RPT-41 totals and tie-out, the GPB-3 point-in-time
equivalence oracle) and ``replay`` (the D-31 mode (b) plan contract and its validation).
Commands, jobs, routes and the promotion subject are the database slice of lane F-LMG and are
not here.
"""
