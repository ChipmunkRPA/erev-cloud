"""Golden parity runner support (docs/dev-guide.md §9.6 DG-PAR-01 to DG-PAR-11; §4.4 DG-MK-parity;
BUILD_SPEC GPA-1).

- ``integrity``: the cases of ``golden-tests.json`` joined with ``deviations.json`` (DG-PAR-01) and
  the DG-PAR-03 preconditions;
- ``scenario``: the DG-PAR-04 world and the replay of the golden steps through the legacy v1 import
  pipeline;
- ``values``: the DG-PAR-05 full-precision value sources and the reader of each built kind;
- ``compare``: the DG-PAR-07 tolerances and mismatches;
- ``report``: the ``make parity`` driver and the DG-PAR-08 report.

This package is test support. Product code never imports it, and it writes only under ``.run/``.
"""
