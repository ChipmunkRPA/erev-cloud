"""General ledger adapters (05 §5.2 ``GLAdapter``, ADP-10 to ADP-15; BUILD_SPEC CLO-13, DIN-14,
CLO-15): ``csv.CsvGl`` (``CSV_GL``) writes the REQ-JE-011 file; ``netsuite.NetSuiteGl``
(``NETSUITE``) reads the ERP's chart of accounts and dimension values for a ``COA_SYNC`` run, posts
journal chunks by their external id and pulls the trial balance; ``quickbooks.QuickBooksGl``
(``QUICKBOOKS_ONLINE``) posts journal chunks under a deterministic request id and pulls the trial
balance — both exercised only against their in-process mocks in 1.0; ``protocol`` re-exports the
port. Composition roots register one factory per E-37 literal with
``erev_api.domain.journals.ports.register_gl_adapter`` (``connection_factory`` for an adapter that
reaches a connection's ``base_url``) and the chart source with ``netsuite.register``."""
