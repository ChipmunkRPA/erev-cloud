from uuid import UUID

import pytest
from erev_api.domain.forecast.history import predecessors
from erev_api.problems import Problem


def edge(source: int, target: int, status: str = "SUCCEEDED"):
    return {
        "source_tenant_id": UUID(int=source),
        "target_tenant_id": UUID(int=target),
        "status": status,
    }


def test_only_successful_connected_predecessors_are_readable():
    assert predecessors(
        UUID(int=3), [edge(1, 2), edge(2, 3), edge(1, 4, "FAILED"), edge(8, 9)]
    ) == (
        UUID(int=3),
        UUID(int=2),
        UUID(int=1),
    )


@pytest.mark.parametrize("edges", [[edge(1, 2), edge(2, 1)], [edge(1, 2), edge(3, 2)]])
def test_corrupt_lineage_is_refused(edges):
    with pytest.raises(Problem):
        predecessors(UUID(int=2), edges)
