"""The scope of an SSP calculator run in a sandbox copy (item SSP-ENTITY-SCOPE-1; 04 T-REF-32 rev
1.277; supervisor ruling R-98; ``snapshot_dataset.SCOPE_ARRAYS``).

T-REF-32 is COPIED into a sandbox. ``ssp_calculator_run.entity_ids`` holds the entities the run's
provider read, and a run is read only by a reader whose ``contract.read`` covers EVERY one of them
(``calculator.reaches_run``); NULL is a run of every entity. That makes the set a requirement, as
T-IMP-02 ``named_entity_ids`` is, and not a grant: the copy must never shorten it.
"""

from __future__ import annotations

from uuid import UUID

from erev_api.db.tables import ssp_calculator_run
from erev_api.domain.platform import snapshot_dataset as sd

INV = sd.inventory()
SCOPE = ("ssp_calculator_run", "entity_ids")


def test_ssp_entity_scope_1_a_runs_scope_is_never_shortened_by_a_sandbox_copy() -> None:
    """A run over two entities copied as a run over one would be read in the sandbox by a reader
    of that one alone, with the other entity's order in its observations. A set that loses an
    element to the cut is exported NULL — a run of every entity, read by a holder for all entities
    alone — for a partial and a complete cut alike, and the copy is not refused; a set that loses
    nothing and a run of every entity are exported as they are.

    No copy loses an element as the run is built — the set is written at INSERT, and the run and
    its entities are both cut by ``created_at`` — so this is the rule the inventory states for
    the column, held where the exporter applies it."""
    e_kept, e_cut, e_other = UUID(int=1), UUID(int=2), UUID(int=3)
    whole, partial, complete, every = (UUID(int=n) for n in range(11, 15))
    rule = sd.SCOPE_ARRAYS[SCOPE]
    assert rule.every_element_required and rule.paired_flag is None
    assert sd.ARRAY_REFERENCES[SCOPE] == "legal_entity"
    # the unresolved form is NULL, so the column can hold it, and both rows are cut alike
    assert ssp_calculator_run.c.entity_ids.nullable
    assert sd.CUTOFF_RULES["ssp_calculator_run"] == sd.CUTOFF_RULES["legal_entity"]
    source = {
        "legal_entity": [{"id": e_kept}, {"id": e_cut}, {"id": e_other}],
        "ssp_calculator_run": [
            {"id": whole, "entity_ids": [e_kept, e_other]},
            {"id": partial, "entity_ids": [e_kept, e_cut]},
            {"id": complete, "entity_ids": [e_cut]},
            {"id": every, "entity_ids": None},
        ],
    }
    cut = {**source, "legal_entity": [{"id": e_kept}, {"id": e_other}]}  # e_cut after known_at
    result = sd.apply_parent_cutoff(INV, source, cut)
    stored = {row["id"]: row["entity_ids"] for row in result.kept["ssp_calculator_run"]}
    assert stored == {
        whole: [e_kept, e_other],
        partial: None,  # never [e_kept]: a reader of e_kept alone must not gain the run
        complete: None,  # and no refusal of the whole copy
        every: None,
    }
    assert result.dropped_elements == {"ssp_calculator_run.entity_ids": 2}
    assert result.unrepresentable == () and result.broken == ()
