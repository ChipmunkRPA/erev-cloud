"""Historical role definitions cannot be replaced by today's permission matrix."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from erev_api.domain.reports.evidence_access_roles import RoleDefinition, RoleMatrix, files
from pydantic import ValidationError

NOW = datetime(2026, 10, 19, 12, tzinfo=UTC)


def definition(**changes: object) -> RoleDefinition:
    return RoleDefinition.model_validate(
        {
            "id": UUID(int=1),
            "code": "auditor",
            "name": "Auditor",
            "is_active": True,
            "created_at": NOW - timedelta(days=20),
            "updated_at": NOW - timedelta(days=1),
            "permissions": ["audit.read", "report.run"],
            **changes,
        }
    )


def test_snapshot_keeps_inactive_roles_and_permissions_without_memberships() -> None:
    row = definition(is_active=False)
    source = RoleMatrix(tenant_id=UUID(int=2), as_of=NOW, known_at=NOW, roles=(row,))
    assert files(source)[0].path == "access/role_permission_matrix.json"
    restored = RoleMatrix.model_validate_json(source.model_dump_json())
    assert files(restored) == files(source)
    assert restored.roles[0].is_active is False
    assert restored.roles[0].permissions == ("audit.read", "report.run")


@pytest.mark.parametrize(
    "roles",
    [
        (definition(), definition()),
        (definition(updated_at=NOW + timedelta(seconds=1)),),
        (definition(created_at=NOW + timedelta(seconds=1), updated_at=NOW + timedelta(seconds=1)),),
        (definition(permissions=["audit.read", "audit.read"]),),
    ],
)
def test_unprovable_or_duplicated_definitions_refuse(roles: tuple[RoleDefinition, ...]) -> None:
    with pytest.raises(ValidationError):
        RoleMatrix(tenant_id=UUID(int=2), as_of=NOW, known_at=NOW, roles=roles)
