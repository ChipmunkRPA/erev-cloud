"""The lock under which a configuration version is made open again (PRD SM-04; dev-guide
DG-KRN-REG-06 rev 1.166; the supervisor's ruling of 2026-10-01 on the pre-build line of item
REG-VERSION-WHOLE-SET-1, point E).

A create makes the next version of a scope open, and ``lifecycle.reopen`` makes a rejected or
withdrawn one open again. Both first look for another open version, so both must take the lock
under which that look is decided — otherwise a reopening misses a create that has not committed
and two versions of one scope are open. Two sessions prove the mechanism for registry versions
(``tests/domain/policies/test_registry_whole_set.py``, which also holds the witness of the row
lock that serialises rule set versions). This module pins, without a database:

* ``lifecycle.reopen`` takes the kind's ``serialise`` lock BEFORE it looks for an open version;
* the three kinds whose create takes an advisory lock and reads the versions without locking them
  supply that same lock — the first statement of their create — as ``serialise``: registry
  versions (per scope key), account mapping versions (per tenant), import mapping profile versions
  (per code);
* the two kinds whose create locks every version row of the scope supply none: rule set and
  obligation template versions. The version being reopened is one of the rows their create waits
  for, and its row lock is held by every caller of ``reopen``;
* a kind's own refusal of a reopening (``ConfigVersionKind.reopenable``; PRD ERR-92 for a
  registry version, the only kind that has one) is raised under that lock and before the look: a
  version that can never be reopened is not told to wait for another one; and it is asked again
  after a look that found no open version, before anything is written — a publication takes no
  such lock and may commit between the first read and the look;
* a create of a registry version takes the key's lock and looks for an open version before it
  reads anything else — the predecessor its statement is decided from is read after them
  (``presets.claim_key``; finding 5 of the independent review of 2026-10-01).
"""

from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace
from typing import Any
from uuid import UUID

import pytest
from erev_api.auth.principal import system_principal
from erev_api.domain.imports import mapping_profiles
from erev_api.domain.policies import lifecycle, registry_versions, rule_sets, templates
from erev_api.domain.reference import commands as reference_commands
from erev_api.domain.reference import mapping
from erev_api.enums import BookCode, ConfigStatus, RegistryCategory, RegistryScope
from erev_api.problems import Problem, ProblemError
from erev_api.registry import presets
from erev_api.registry import versions as registry_kernel
from erev_api.schemas.account_mappings import AccountMappingIn
from sqlalchemy.dialects import postgresql

TENANT = UUID(int=0x7E)
ENTITY = UUID(int=0xE1)


class _Recorder:
    """A session that records the statements it is given and answers nothing."""

    def __init__(self) -> None:
        self.statements: list[Any] = []

    def execute(self, statement: Any, *_: Any, **__: Any) -> Any:
        self.statements.append(statement)
        return None


def _uow() -> Any:
    # The caller is the tenant's SYSTEM principal: a create asks who authors a version of its
    # scope before it claims the key (``registry_versions.require_authority``), and SYSTEM
    # acts for the tenant.
    return SimpleNamespace(session=_Recorder(), principal=system_principal(TENANT))


def _advisory_key(statement: Any) -> str:
    """The key of a ``pg_advisory_xact_lock(hashtextextended(<key>, 0))`` statement."""
    compiled = statement.compile(dialect=postgresql.dialect())
    assert "pg_advisory_xact_lock(hashtextextended(" in str(compiled), str(compiled)
    [key] = [value for value in compiled.params.values() if isinstance(value, str)]
    return key


def _first_statement_of(create: Any) -> Any:
    """The first statement a create executes; the recorder answers nothing, so the create stops
    at its next read."""
    uow = _uow()
    with pytest.raises((AttributeError, TypeError)):
        create(uow)
    return uow.session.statements[0]


def test_reopen_takes_the_kinds_lock_before_it_looks_for_an_open_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    def look(*_: Any) -> bool:
        calls.append("look")
        return True  # another version is open: the reopening is refused after the look

    monkeypatch.setattr(lifecycle, "_open_elsewhere", look)
    version = {"id": UUID(int=1), "status": ConfigStatus.REJECTED.value}
    locked = replace(
        registry_versions.KIND,
        serialise=lambda _uow, _version: calls.append("lock"),
        reopenable=lambda _uow, _version: calls.append("own refusal"),
    )
    with pytest.raises(Problem) as refused:
        lifecycle.reopen(_uow(), locked, version)
    assert refused.value.errors[0].rule_id == lifecycle.RULE_OPEN_VERSION
    assert calls == ["lock", "own refusal", "look"]
    calls.clear()
    bare = replace(registry_versions.KIND, serialise=None, reopenable=None)
    with pytest.raises(Problem):
        lifecycle.reopen(_uow(), bare, version)
    assert calls == ["look"]


def test_a_kinds_own_refusal_of_a_reopening_is_raised_before_the_look(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """PRD ERR-92 by its mechanism: ``reopenable`` raises under the kind's lock and the look for
    an open version never runs — a version that can never be reopened is not answered "Another
    version is open. Finish it or withdraw it first." Only a registry version has such a refusal;
    the other four kinds hold their whole content in their own rows."""
    calls: list[str] = []
    monkeypatch.setattr(lifecycle, "_open_elsewhere", lambda *_: calls.append("look") or True)

    def refuse(_uow: Any, _version: Any) -> None:
        calls.append("own refusal")
        raise Problem(
            "invalid-transition",
            errors=[ProblemError(field="status", rule_id="ITS_OWN", message="Never again.")],
        )

    kind = replace(
        registry_versions.KIND,
        serialise=lambda _uow, _version: calls.append("lock"),
        reopenable=refuse,
    )
    version = {"id": UUID(int=1), "status": ConfigStatus.REJECTED.value}
    with pytest.raises(Problem) as refused:
        lifecycle.reopen(_uow(), kind, version)
    assert refused.value.errors[0].rule_id == "ITS_OWN"
    assert calls == ["lock", "own refusal"]
    assert registry_versions.KIND.reopenable is not None
    for other in (
        rule_sets.RULE_SET_VERSION_KIND,
        templates.POB_TEMPLATE_VERSION_KIND,
        mapping.ACCOUNT_MAPPING_VERSION_KIND,
        mapping_profiles.KIND,
    ):
        assert other.reopenable is None, other.object_type


def test_a_kinds_own_refusal_is_asked_again_after_the_look(monkeypatch: pytest.MonkeyPatch) -> None:
    """The answer that stands is the one given after the look: with the lock held and no version
    of the scope open, none can be published before the reopening commits. A refusal that passes
    before the look and raises after it stops the reopening before any statement is written."""
    calls: list[str] = []
    monkeypatch.setattr(lifecycle, "_open_elsewhere", lambda *_: bool(calls.append("look")))

    def refuse_after_the_look(_uow: Any, _version: Any) -> None:
        calls.append("own refusal")
        if "look" in calls:
            raise Problem(
                "invalid-transition",
                errors=[ProblemError(field="status", rule_id="ITS_OWN", message="Too late.")],
            )

    kind = replace(
        registry_versions.KIND,
        serialise=lambda _uow, _version: calls.append("lock"),
        reopenable=refuse_after_the_look,
    )
    uow = _uow()
    with pytest.raises(Problem) as refused:
        lifecycle.reopen(uow, kind, {"id": UUID(int=1), "status": ConfigStatus.REJECTED.value})
    assert refused.value.errors[0].rule_id == "ITS_OWN"
    assert calls == ["lock", "own refusal", "look", "own refusal"]
    assert uow.session.statements == []


def test_a_registry_create_claims_its_key_before_it_reads_a_predecessor() -> None:
    """Finding 5 of the independent review of 2026-10-01: ``create_policy`` and the preset's
    create take the key's advisory lock as their first statement and look for an open version as
    their second (``presets.claim_key``); the recorder answers nothing, so they stop at that
    look — no predecessor was read before it."""
    expected = f"erev.registry_version:{TENANT}:ACCOUNTING_POLICY:TENANT::"
    creates = (
        lambda uow: registry_versions.create_policy(
            uow,
            category=RegistryCategory.ACCOUNTING_POLICY,
            scope=RegistryScope.TENANT,
            entity_code=None,
            book_code=None,
            values={},
            effective_from=None,
        ),
        lambda uow: registry_versions.create_legacy_parity_preset(
            uow, scope=RegistryScope.TENANT, entity_code=None, book_code=None
        ),
    )
    for create in creates:
        uow = _uow()
        with pytest.raises((AttributeError, TypeError)):
            create(uow)
        lock, look = uow.session.statements
        assert _advisory_key(lock) == expected
        compiled = str(look.compile(dialect=postgresql.dialect()))
        assert "registry_version.status" in compiled and '"values"' not in compiled, compiled


def test_a_registry_version_is_reopened_under_the_lock_of_its_scope_key() -> None:
    assert registry_versions.KIND.serialise is not None
    uow = _uow()
    registry_versions.KIND.serialise(
        uow,
        {
            "category": "PRACTICAL_EXPEDIENT",
            "scope": "ENTITY",
            "book_code": None,
            "entity_id": ENTITY,
        },
    )
    [taken] = uow.session.statements
    expected = f"erev.registry_version:{TENANT}:PRACTICAL_EXPEDIENT:ENTITY::{ENTITY}"
    assert _advisory_key(taken) == expected
    created = _first_statement_of(
        lambda uow: presets.create_draft_version(
            uow,
            category=RegistryCategory.PRACTICAL_EXPEDIENT,
            scope=RegistryScope.ENTITY,
            book_code=None,
            entity_id=ENTITY,
            values={},
            preset_code=None,
            effective_from=None,
        )
    )
    assert _advisory_key(created) == expected
    # A BOOK version's key names its book; a TENANT version's key neither book nor entity.
    uow = _uow()
    registry_versions.KIND.serialise(
        uow,
        {
            "category": "ACCOUNTING_POLICY",
            "scope": "BOOK",
            "book_code": BookCode.IFRS15.value,
            "entity_id": None,
        },
    )
    assert _advisory_key(uow.session.statements[0]) == (
        f"erev.registry_version:{TENANT}:ACCOUNTING_POLICY:BOOK:IFRS15:"
    )


def test_an_account_mapping_version_is_reopened_under_the_tenants_lock() -> None:
    kind = mapping.ACCOUNT_MAPPING_VERSION_KIND
    assert kind.serialise is not None
    uow = _uow()
    kind.serialise(uow, {"id": UUID(int=2)})
    [taken] = uow.session.statements
    assert _advisory_key(taken) == f"erev.account_mapping_version:{TENANT}"
    created = _first_statement_of(
        lambda uow: reference_commands.create_account_mapping_version(
            uow, body=AccountMappingIn(name="Mapping 2")
        )
    )
    assert _advisory_key(created) == _advisory_key(taken)


def test_an_import_mapping_profile_version_is_reopened_under_the_lock_of_its_code() -> None:
    kind = mapping_profiles.KIND
    assert kind.serialise is not None
    uow = _uow()
    kind.serialise(uow, {"id": UUID(int=3), "code": "ORDERS-EU"})
    [taken] = uow.session.statements
    assert _advisory_key(taken) == f"import_mapping_profile:{TENANT}:ORDERS-EU"
    created = _first_statement_of(
        lambda uow: mapping_profiles.create_profile(
            uow,
            code="ORDERS-EU",
            name="Orders, Europe",
            template_code="orders_v2",
            mappings={},
            effective_from=None,
        )
    )
    assert _advisory_key(created) == _advisory_key(taken)


def test_the_published_version_of_a_key_is_read_for_update_when_the_hook_asks() -> None:
    """The approval hook re-checks a registry version's basis with the PUBLISHED version of its
    key locked (``registry_versions._on_approved``; supervisor ruling R-117 (b) rule 3): asked
    ``for_update``, the read is a ``FOR UPDATE`` of that row; a plain read takes no lock."""
    key = {"category": "PLATFORM", "scope": "TENANT", "book_code": None, "entity_id": None}
    compiled = []
    for for_update in (True, False):
        session = _Recorder()
        with pytest.raises(AttributeError):  # the recorder answers nothing to read
            registry_kernel.published_of_key(session, **key, for_update=for_update)  # type: ignore[arg-type]
        [statement] = session.statements
        compiled.append(str(statement.compile(dialect=postgresql.dialect())))
    locked, plain = compiled
    assert locked.rstrip().endswith("FOR UPDATE") and "status" in locked
    assert "FOR UPDATE" not in plain


def test_rule_set_and_template_versions_supply_no_lock() -> None:
    """Their create locks the parent row and then EVERY version row of the parent ``FOR UPDATE``
    (``commands.create_rule_set_version``, ``commands.create_pob_template_version``) — the
    rejected or withdrawn version among them, whose row lock the reopening holds
    (``rule_sets.lock_version``, ``templates.lock_version``). The two wait for each other on that
    row; a lock on the parent's row in ``reopen`` would be taken after the version's and invert
    the create's order."""
    assert rule_sets.RULE_SET_VERSION_KIND.serialise is None
    assert templates.POB_TEMPLATE_VERSION_KIND.serialise is None
