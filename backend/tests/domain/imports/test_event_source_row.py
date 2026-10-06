"""An imported event names its source row on every read of the event (04 §16.3 API-S-Event
``source_row``, rev 1.273; T-IMP-04; the supervisor's ruling of 2026-10-02; BUILD_SPEC CTR-5,
CTR-15, DIN-3).

``GET /obligations/{id}/events`` is the route the Events panel of an obligation reads. Until rev
1.273 it answered a model of its own whose ``source_row`` was null for every event. Measured there
for the booking an approved import appended: null, while ``GET /contracts/{id}/events`` named the
row of the file — so the panel could not lead from an imported event back to its source. The
route now answers API-S-Event whole: the events resource's model, built by its builder.

World: ``test_commit.j03`` with its contract importer — the CSV v2 ``contracts`` file books
SF-ORD-30001 with two lines, O1 and O2. DB-bound.
"""

from __future__ import annotations

import test_commit as commits
from erev_api.db.tables import contract, obligation
from sqlalchemy import select
from support.factories import ImportWorld, J03World
from support.reference import assign, get

app = commits.app
files = commits.files
j03 = commits.j03
contract_importer = commits.contract_importer


def test_api_s_event_is_whole_on_the_obligations_route_for_an_imported_event(
    j03: J03World, contract_importer: ImportWorld
) -> None:
    import_id = commits.diffed(
        contract_importer, "sf-ord-30001.csv", commits.contracts_csv(j03.customer_id), "contracts"
    )
    assign(j03.priya.member, "revenue_reviewer")
    done = commits.committed(contract_importer, import_id, j03.priya)
    assert done["status"] == "COMMITTED", done
    (booked,) = contract_importer.rows(
        select(contract.c.id).where(contract.c.external_id == "SF-ORD-30001")
    )
    reader = j03.place.author
    listed = get(j03.app, f"/api/v1/contracts/{booked['id']}/events", reader)
    assert listed.status_code == 200, listed.text
    (event,) = listed.json()["items"]
    source = {"import_upload_id": import_id, "sheet": "CSV", "row_number": 2}
    assert (event["event_type"], event["origin"], event["source_row"]) == (
        "CONTRACT_BOOKED",
        "IMPORT",
        source,
    )
    obligations = contract_importer.rows(
        select(obligation.c.id, obligation.c.obligation_key).where(
            obligation.c.contract_id == booked["id"]
        )
    )
    assert sorted(str(row["obligation_key"]) for row in obligations) == ["O1", "O2"]

    for row in obligations:
        key = str(row["obligation_key"])
        panel = get(j03.app, f"/api/v1/obligations/{row['id']}/events", reader)
        assert panel.status_code == 200, panel.text
        (item,) = panel.json()["items"]
        # the status first: before the rule the member was null on this route
        assert item["source_row"] == source, key
        assert item == event, key  # the event, whole, as the events resource answers it
