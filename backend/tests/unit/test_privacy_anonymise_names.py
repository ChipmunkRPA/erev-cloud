"""05 PRV-07 a erased-identity forms (BUILD_SPEC SOP-5). CPU only; the command itself is exercised
by ``backend/tests/domain/platform/test_privacy_commands.py`` against a database."""

from __future__ import annotations

import hashlib
import re
from uuid import UUID, uuid4

from erev_api.domain.platform import users
from erev_api.domain.platform.privacy import (
    ANONYMISE_ACTION,
    ERASED_DOMAIN,
    completion_next_step,
    erased_display_name,
    erased_email,
    pending_secondary_memberships,
)
from erev_api.privacy.classification import CLASSIFICATION, Erasure
from erev_api.privacy.patterns import EMAIL
from sqlalchemy.dialects import postgresql

USER_ID = UUID("2a1f3c4d-0000-4000-8000-000000000001")


def test_prv_07a_erased_display_name_is_the_first_8_hex_of_sha256() -> None:
    digest = hashlib.sha256(str(USER_ID).encode("utf-8")).hexdigest()
    assert erased_display_name(USER_ID) == f"Erased user {digest[:8]}"
    assert re.fullmatch(r"Erased user [0-9a-f]{8}", erased_display_name(USER_ID))
    assert erased_display_name(USER_ID) == erased_display_name(USER_ID)
    assert erased_display_name(USER_ID) != erased_display_name(UUID(int=1))


def test_prv_07a_erased_email_is_unique_and_undeliverable() -> None:
    assert erased_email(USER_ID) == f"erased+{USER_ID}@invalid.erev"
    assert ERASED_DOMAIN == "invalid.erev"
    assert EMAIL.fullmatch(erased_email(USER_ID)), "the placeholder stays a well-formed address"
    assert erased_email(USER_ID) != erased_email(UUID(int=1))


def test_the_rule_knows_an_erased_identity_by_the_address_the_erasure_writes() -> None:
    """D-80 rule 5 leaves the label of an erased identity where it is (04 T-PLT-02 rev 1.316):
    ``users.ERASED``, the rule's mark of such an identity, is the address ``erased_email`` writes
    for the row's own id — the same parts in the same order — so the predicate and its writer do
    not drift apart unseen. PostgreSQL casts a uuid to the text ``str(UUID)`` gives."""
    compiled = users.ERASED.compile(
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    assert " ".join(str(compiled).split()) == (
        "erev.app_user.email = concat('erased+', CAST(erev.app_user.id AS TEXT), '@invalid.erev')"
    )
    assert erased_email(USER_ID) == "erased+" + str(USER_ID) + "@" + ERASED_DOMAIN


def test_prv_07a_action_and_catalogue_agree() -> None:
    """The columns the command rewrites are the catalogue's ANONYMISE erasures."""
    assert ANONYMISE_ACTION == "app_user.anonymise"
    # 05 PRV-07 a rev 1.47: the erasure clears the provider subject with the external id.
    rewritten = {
        "email",
        "display_name",
        "password_hash",
        "external_id",
        "identity_provider_subject",
    }
    anonymised = {
        column
        for (table, column), entry in CLASSIFICATION.items()
        if table == "app_user" and entry.erasure is Erasure.ANONYMISE
    }
    assert anonymised == rewritten


def test_prv_07a_pending_secondary_memberships_is_the_work_still_owed() -> None:
    """Codex P8-PRV07-COMPLETE-1: the acting tenant's row and rows already REMOVED (an earlier
    attempt's completed part) are excluded, so a repeated command never audits a removal twice;
    the enumeration order (tenant id) is kept."""
    acting, other, third = UUID(int=1), UUID(int=2), UUID(int=3)
    m_acting, m_other, m_third, m_removed = (UUID(int=n) for n in (11, 12, 13, 14))
    memberships = [
        (acting, m_acting, "ACTIVE"),
        (other, m_other, "SUSPENDED"),
        (third, m_third, "INVITED"),
        (UUID(int=4), m_removed, "REMOVED"),
    ]
    assert pending_secondary_memberships(memberships, acting) == (
        (other, m_other),
        (third, m_third),
    )
    assert pending_secondary_memberships([], acting) == ()
    assert pending_secondary_memberships([(acting, m_acting, "ACTIVE")], acting) == ()
    completed_elsewhere = [(other, m_other, "REMOVED"), (third, m_third, "INVITED")]
    assert pending_secondary_memberships(completed_elsewhere, acting) == ((third, m_third),)


def test_prv_07a_completion_next_step_names_every_owed_workspace() -> None:
    """Codex production-20260921-2359 / supervisor: the 200 response tells the administrator that
    a second run is owed and where; nothing when nothing is owed; no background delivery claimed."""
    assert completion_next_step([]) is None
    b, c = uuid4(), uuid4()
    text = completion_next_step([b, c])
    assert text is not None
    assert "again" in text and "new Idempotency-Key" in text
    assert str(b) in text and str(c) in text and "2 other workspace(s)" in text
    assert "removed membership" in text and "Nothing completes in the background" in text
