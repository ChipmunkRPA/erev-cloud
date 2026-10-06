"""DG-KRN-AUD-09: the contract key of an audit event (04 T-PLT-19 and §1.7, rev 1.154; ruling
R-108).

``audit.contract_key.keyed`` is the one way the key enters ``detail``; ``audit.writer.build_event``
calls it for every event.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from erev_api.audit import contract_key
from erev_api.audit.writer import AuditActor, build_event
from erev_api.enums import AuditOutcome, PrincipalKind

A = UUID("00000000-0000-7000-8000-00000000000a")
B = UUID("00000000-0000-7000-8000-00000000000b")
TENANT = UUID("00000000-0000-7000-8000-0000000000f0")
AT = datetime(2026, 9, 30, 12, 0, tzinfo=UTC)


def test_dg_krn_aud_09_one_contract_is_stated_as_contract_id() -> None:
    assert contract_key.keyed("modification", {"x": 1}, contract_id=A) == {
        "x": 1,
        "contract_id": str(A),
    }
    # One contract reads the same whichever keyword the writer used.
    assert contract_key.keyed("modification", None, contract_ids=[A]) == {"contract_id": str(A)}
    assert contract_key.keyed("modification", None, contract_ids=[A, A]) == {"contract_id": str(A)}


def test_dg_krn_aud_09_several_contracts_are_stated_sorted_and_without_contract_id() -> None:
    found = contract_key.keyed("combination_group", {"x": 1}, contract_ids=[B, A, B])
    assert found == {"x": 1, "contract_ids": [str(A), str(B)]}
    assert "contract_id" not in found


def test_dg_krn_aud_09_an_event_of_a_contract_object_without_a_contract_is_refused() -> None:
    for object_type in sorted(contract_key.ALWAYS):
        with pytest.raises(ValueError, match="names its contract"):
            contract_key.keyed(object_type, {"x": 1})
        with pytest.raises(ValueError, match="names its contract"):
            contract_key.keyed(object_type, None, contract_ids=[])


def test_dg_krn_aud_09_a_type_that_may_name_no_contract_and_any_other_type_pass_unkeyed() -> None:
    for object_type in sorted(contract_key.WHERE_NAMED | contract_key.OTHER):
        assert contract_key.keyed(object_type, {"x": 1}) == {"x": 1}
        assert contract_key.keyed(object_type, None, contract_ids=[]) == {}
    # An event of another object may still concern a contract; the key is then stated the same way.
    assert contract_key.keyed("file_attachment", None, contract_id=A) == {"contract_id": str(A)}


def test_dg_krn_aud_09_the_key_has_one_way_in() -> None:
    for member in ("contract_id", "contract_ids"):
        with pytest.raises(ValueError, match="not inside detail"):
            contract_key.keyed("tenant", {member: str(A)})
        with pytest.raises(ValueError, match="not inside detail"):
            contract_key.keyed("modification", {member: str(A)}, contract_id=A)
    with pytest.raises(ValueError, match="one contract or several, not both"):
        contract_key.keyed("modification", None, contract_id=A, contract_ids=[A, B])


def test_dg_krn_aud_09_scoped_is_the_two_contract_lists() -> None:
    assert contract_key.scoped("modification") and contract_key.scoped("estimate_version")
    assert not contract_key.scoped("tenant") and not contract_key.scoped("unknown_table")


def test_dg_krn_aud_09_a_denied_event_is_never_refused_for_want_of_a_key() -> None:
    """DG-KRN-AUTH-05: a permission is refused before the object is read (the attachment guard
    names the subject it was asked for), and that refusal must be recorded, not turned into an
    error."""
    for object_type in sorted(contract_key.ALWAYS):
        assert contract_key.keyed(object_type, {"x": 1}, required=False) == {"x": 1}
    denied = _event("contract", outcome=AuditOutcome.DENIED, detail={"permission": "p"})
    assert denied["detail"] == {"permission": "p"} and denied["outcome"] == "DENIED"
    # A writer that holds the contract of a refused command still names it.
    assert _event("contract", outcome=AuditOutcome.DENIED, contract_id=A)["detail"] == {
        "contract_id": str(A)
    }
    with pytest.raises(ValueError, match="names its contract"):
        _event("contract", outcome=AuditOutcome.FAILED)


def _event(object_type: str, **keywords: object) -> dict[str, object]:
    actor = AuditActor(
        id=None,
        kind=PrincipalKind.SYSTEM,
        roles=(),
        auth_method=None,
        mfa_verified=False,
        on_behalf_of_id=None,
        api_client_id=None,
        support_grant_id=None,
        source_ip=None,
        request_id="request-1",
    )
    return build_event(
        tenant_id=TENANT,
        actor=actor,
        occurred_at=AT,
        action=f"{object_type}.update",
        object_type=object_type,
        object_id=None,
        **keywords,  # type: ignore[arg-type]
    )


def test_dg_krn_aud_09_build_event_states_the_key_in_detail() -> None:
    assert _event("contract_hold", contract_id=A, detail={"reason": "R"})["detail"] == {
        "reason": "R",
        "contract_id": str(A),
    }
    assert _event("subledger_posting", contract_ids=[B, A])["detail"] == {
        "contract_ids": [str(A), str(B)]
    }
    assert _event("tenant")["detail"] == {}
    with pytest.raises(ValueError, match="names its contract"):
        _event("contract_hold")
