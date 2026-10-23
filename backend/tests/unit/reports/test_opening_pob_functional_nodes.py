"""Foreign opening source coverage must include cancelling documents, not only net quantity."""

from datetime import date
from decimal import Decimal as D
from types import SimpleNamespace as NS

import pytest

from erev_api.domain.reports.opening_pob_functional_nodes import read
from erev_api.problems import Problem


def test_cancelling_transaction_documents_keep_functional_difference():
    period = NS(key="P01", end=date(2026, 1, 31))
    nodes = {}
    for key, txn, functional, sign in (("INV", "100", "110", "1"), ("CM", "-100", "100", "-1")):
        identity = f"billing_document_attributed@{key}:C/P1:-"
        nodes[identity] = NS(id=identity, currency="EUR", value=txn, params={"as_of": "2026-01-01"})
        identity = f"billing_obligation_activity_functional:{key}@C/P1:P01"
        nodes[identity] = NS(
            id=identity,
            currency="USD",
            value=functional,
            params={
                "source_key": key,
                "obligation_subject": "C/P1",
                "sign": sign,
            },
        )
    kwargs = dict(
        subject="C/P1", period=period, txn_currency="EUR", currency="USD", billed=D(0), revenue=D(0)
    )
    billed, revenue, inputs = read(nodes, **kwargs)
    assert (billed, revenue, len(inputs)) == (D("10"), D(0), 4)
    incomplete = {
        key: value
        for key, value in nodes.items()
        if not key.startswith("billing_obligation_activity_functional:")
    }
    with pytest.raises(Problem):
        read(incomplete, **kwargs)
    wrong_currency = dict(nodes)
    key = "billing_obligation_activity_functional:INV@C/P1:P01"
    wrong_currency[key] = NS(**{**vars(nodes[key]), "currency": "GBP"})
    with pytest.raises(Problem):
        read(wrong_currency, **kwargs)
