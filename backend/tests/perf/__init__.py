"""Performance harness (BUILD_SPEC PRF-3 to PRF-6; dev-guide DG-PERF-01 to DG-PERF-08).

A regular package so that its modules import as ``perf.…`` and the shared ``support`` package stays
the one under ``backend/tests`` (pytest's prepend import mode). Every test here carries the ``perf``
marker and is deselected unless ``EREV_PERF_RUN=1`` (``make perf``, DG-MK-perf).
"""
