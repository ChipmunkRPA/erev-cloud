"""Rule set and configuration test case queries (04 §15.3 API-R-25, API-R-57, §16.14 list
additions; dev-guide DG-CMD-13; BUILD_SPEC RFD-4, RFD-5). Reads run in a read-only tenant session;
the ``*_out`` builders also serve command responses inside the command's transaction."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from erev_api.db.session import tenant_session
from erev_api.db.tables import (
    pob_template,
    pob_template_version,
    rule,
    rule_set,
    rule_set_version,
    rule_test_case,
)
from erev_api.domain.platform.approval_queries import Page
from erev_api.domain.policies import rule_sets, templates
from erev_api.problems import Problem

if TYPE_CHECKING:
    from erev_api.auth.keyring import KeyRing
    from erev_api.auth.principal import RequestContext
    from erev_api.files.store import FileStore


def _exists(session: Session, statement: Select[Any]) -> None:
    if session.execute(statement).first() is None:
        raise Problem("not-found")


def rule_set_out(session: Session, rule_set_id: UUID) -> dict[str, Any]:
    row = (
        session.execute(select(rule_set).where(rule_set.c.id == rule_set_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return rule_sets.rule_set_outs(session, [dict(row)])[0]


def version_out(
    session: Session, version_id: UUID, *, files: FileStore, keyring: KeyRing
) -> dict[str, Any]:
    row = (
        session.execute(select(rule_set_version).where(rule_set_version.c.id == version_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return rule_sets.version_outs(session, [dict(row)], files=files, keyring=keyring)[0]


def rule_out(session: Session, rule_id: UUID) -> dict[str, Any]:
    row = session.execute(select(rule).where(rule.c.id == rule_id)).mappings().one()
    return rule_sets.rule_out(dict(row))


def case_out(session: Session, case_id: UUID) -> dict[str, Any]:
    row = (
        session.execute(select(rule_test_case).where(rule_test_case.c.id == case_id))
        .mappings()
        .one()
    )
    return rule_sets.case_out(dict(row))


def list_rule_sets[P: Page](
    ctx: RequestContext, *, page: Callable[[Session, Select[Any]], P]
) -> tuple[P, list[dict[str, Any]]]:
    """One page of rule sets with ``current_version`` and ``latest_version``."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        result = page(session, select(rule_set))
        return result, rule_sets.rule_set_outs(session, result.items)


def get_rule_set(ctx: RequestContext, rule_set_id: UUID) -> dict[str, Any]:
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return rule_set_out(session, rule_set_id)


def list_versions[P: Page](
    ctx: RequestContext,
    rule_set_id: UUID,
    *,
    page: Callable[[Session, Select[Any]], P],
    files: FileStore,
    keyring: KeyRing,
) -> tuple[P, list[dict[str, Any]]]:
    """One page of the versions of a set; 404 for an unknown set."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        _exists(session, select(rule_set.c.id).where(rule_set.c.id == rule_set_id))
        result = page(
            session,
            select(rule_set_version).where(rule_set_version.c.rule_set_id == rule_set_id),
        )
        return result, rule_sets.version_outs(session, result.items, files=files, keyring=keyring)


def get_version(
    ctx: RequestContext, version_id: UUID, *, files: FileStore, keyring: KeyRing
) -> dict[str, Any]:
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return version_out(session, version_id, files=files, keyring=keyring)


def list_rules[P: Page](
    ctx: RequestContext, version_id: UUID, *, page: Callable[[Session, Select[Any]], P]
) -> tuple[P, list[dict[str, Any]]]:
    """One page of the rules of a version; 404 for an unknown version."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        _exists(session, select(rule_set_version.c.id).where(rule_set_version.c.id == version_id))
        result = page(session, select(rule).where(rule.c.rule_set_version_id == version_id))
        return result, [rule_sets.rule_out(item) for item in result.items]


def rule_key_exists(ctx: RequestContext, version_id: UUID, rule_key: str) -> bool:
    """Whether the version holds a rule with ``rule_key``; the upsert route answers 200 then."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        found = session.execute(
            select(rule.c.id).where(
                rule.c.rule_set_version_id == version_id, rule.c.rule_key == rule_key
            )
        ).first()
        return found is not None


def list_rule_test_cases[P: Page](
    ctx: RequestContext, version_id: UUID, *, page: Callable[[Session, Select[Any]], P]
) -> tuple[P, list[dict[str, Any]]]:
    """One page of the example cases of a version; 404 for an unknown version."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        _exists(session, select(rule_set_version.c.id).where(rule_set_version.c.id == version_id))
        result = page(
            session,
            select(rule_test_case).where(
                rule_test_case.c.subject_type == rule_sets.SUBJECT_TYPE,
                rule_test_case.c.subject_id == version_id,
            ),
        )
        return result, [rule_sets.case_out(item) for item in result.items]


def list_config_test_cases[P: Page](
    ctx: RequestContext, *, page: Callable[[Session, Select[Any]], P]
) -> tuple[P, list[dict[str, Any]]]:
    """One page of example cases of every configuration subject type (API-R-57)."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        result = page(session, select(rule_test_case))
        return result, [rule_sets.case_out(item) for item in result.items]


# --- obligation templates (API-R-24; BUILD_SPEC RFD-10) ----------------------------------------


def pob_template_out(session: Session, template_id: UUID) -> dict[str, Any]:
    row = (
        session.execute(select(pob_template).where(pob_template.c.id == template_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return templates.template_outs(session, [dict(row)])[0]


def pob_template_version_out(session: Session, version_id: UUID) -> dict[str, Any]:
    row = (
        session.execute(select(pob_template_version).where(pob_template_version.c.id == version_id))
        .mappings()
        .one_or_none()
    )
    if row is None:
        raise Problem("not-found")
    return templates.version_outs(session, [dict(row)])[0]


def list_pob_templates[P: Page](
    ctx: RequestContext, *, page: Callable[[Session, Select[Any]], P]
) -> tuple[P, list[dict[str, Any]]]:
    """One page of obligation templates with ``current_version`` and ``latest_version``."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        result = page(session, select(pob_template))
        return result, templates.template_outs(session, result.items)


def get_pob_template(ctx: RequestContext, template_id: UUID) -> dict[str, Any]:
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return pob_template_out(session, template_id)


def list_pob_template_versions[P: Page](
    ctx: RequestContext, template_id: UUID, *, page: Callable[[Session, Select[Any]], P]
) -> tuple[P, list[dict[str, Any]]]:
    """One page of the versions of a template; 404 for an unknown template."""
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        _exists(session, select(pob_template.c.id).where(pob_template.c.id == template_id))
        result = page(
            session,
            select(pob_template_version).where(
                pob_template_version.c.pob_template_id == template_id
            ),
        )
        return result, templates.version_outs(session, result.items)


def get_pob_template_version(ctx: RequestContext, version_id: UUID) -> dict[str, Any]:
    with tenant_session(ctx.principal.db_context, read_only=True) as session:
        return pob_template_version_out(session, version_id)
