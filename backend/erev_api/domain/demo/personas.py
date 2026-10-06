"""Demo persona users WLD-U-01 to WLD-U-11 (docs/02-PRD.md §2.3; D-75 PRD Q1; BUILD_SPEC WEB-10,
BS1-D-20).

One named persona per default role, ``<name>@demo.erev``, holding the roles of the PRD §2.3 table in
each tenant group: the legacy parity pack WLD-T-00, the journey tenant WLD-T-01 and the industry
tenants WLD-T-02 to 07. A persona without roles in a group has no membership there. Every assignment
covers all entities. ``tomas`` is the bootstrap Tenant Admin of every demo tenant and invites the
others; ``grace`` approves the custom role ``deal_desk_analyst`` that ``tomas`` prepares.
``validate_personas`` refuses an email outside ``demo.erev`` before the seed writes anything
(WLD-R-04).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType
from typing import Final, Literal

from erev_api.auth.permissions import DEFAULT_ROLES, spec
from erev_api.domain.demo import SeedRefused

TenantGroup = Literal["legacy", "journey", "industry"]
GROUPS: Final[tuple[TenantGroup, ...]] = ("legacy", "journey", "industry")

DEMO_DOMAIN: Final = "demo.erev"  # WLD-R-04, WLD-U-R4
ADMIN: Final = "tomas"  # BS1-D-20: the bootstrap Tenant Admin of every demo tenant
ROLE_APPROVER: Final = "grace"  # BS1-D-20: approves the custom role the admin prepares
_EMAIL: Final = re.compile(r"^[a-z0-9._+-]+@([a-z0-9-]+(?:\.[a-z0-9-]+)+)$")


@dataclass(frozen=True, slots=True)
class CustomRole:
    code: str
    name: str
    description: str
    permissions: tuple[str, ...]


# WLD-U-11 "Deal desk analyst (custom role)"; BS1-D-20 gives it scenario.use.
DEAL_DESK_ANALYST: Final = CustomRole(
    code="deal_desk_analyst",
    name="Deal desk analyst",
    description="Runs what-if scenarios for deal reviews.",
    permissions=("scenario.use",),
)
CUSTOM_ROLES: Final[Mapping[str, CustomRole]] = MappingProxyType(
    {DEAL_DESK_ANALYST.code: DEAL_DESK_ANALYST}
)


@dataclass(frozen=True, slots=True)
class Persona:
    key: str
    wld_id: str
    display_name: str
    email: str
    roles: Mapping[TenantGroup, tuple[str, ...]]  # role codes per group; absent = no membership

    def roles_in(self, group: TenantGroup) -> tuple[str, ...]:
        return self.roles.get(group, ())


def _everywhere(*codes: str) -> Mapping[TenantGroup, tuple[str, ...]]:
    return MappingProxyType(dict.fromkeys(GROUPS, codes))


def _only(**groups: tuple[str, ...]) -> Mapping[TenantGroup, tuple[str, ...]]:
    return MappingProxyType({group: groups[group] for group in GROUPS if group in groups})


# PRD §2.3 table, in WLD-U order.
PERSONAS: Final[tuple[Persona, ...]] = (
    Persona(
        "maya",
        "WLD-U-01",
        "Maya Chen",
        "maya@demo.erev",
        _everywhere("revenue_accountant", "ssp_analyst"),
    ),
    Persona(
        "priya",
        "WLD-U-02",
        "Priya Raman",
        "priya@demo.erev",
        _everywhere("revenue_reviewer", "ssp_approver"),
    ),
    Persona(
        "marcus",
        "WLD-U-03",
        "Marcus Webb",
        "marcus@demo.erev",
        _everywhere("controller", "ssp_approver"),
    ),
    Persona("elena", "WLD-U-04", "Elena Sokolova", "elena@demo.erev", _everywhere("controller")),
    Persona("robert", "WLD-U-05", "Robert Adeyemi", "robert@demo.erev", _everywhere("viewer")),
    Persona("hannah", "WLD-U-06", "Hannah Lindqvist", "hannah@demo.erev", _everywhere("auditor")),
    Persona("samuel", "WLD-U-07", "Samuel Ortiz", "samuel@demo.erev", _only(journey=("auditor",))),
    Persona("tomas", "WLD-U-08", "Tomás Rivera", "tomas@demo.erev", _everywhere("tenant_admin")),
    Persona("grace", "WLD-U-09", "Grace Okafor", "grace@demo.erev", _everywhere("tenant_admin")),
    Persona(
        "nikhil",
        "WLD-U-10",
        "Nikhil Rao",
        "nikhil@demo.erev",
        _only(journey=("integration_admin",), industry=("integration_admin",)),
    ),
    Persona(
        "jordan",
        "WLD-U-11",
        "Jordan Blake",
        "jordan@demo.erev",
        _only(
            journey=("viewer", DEAL_DESK_ANALYST.code), industry=("viewer", DEAL_DESK_ANALYST.code)
        ),
    ),
)


def role_permissions(code: str) -> frozenset[str]:
    """The permissions of a default role or of a demo custom role."""
    if code in DEFAULT_ROLES:
        return DEFAULT_ROLES[code]
    return frozenset(CUSTOM_ROLES[code].permissions)


# PRD WLD-U-R2 (rev 1.153; supervisor ruling R-83 (f), item DEMO-MFA-PREPARER-1): a sign-off needs
# an MFA-verified session whatever the permission's ``requires_mfa`` flag (04 T-CLS-08: the
# preparation of a reconciliation, the sign of a close task), so a persona whose journey signs off
# is enrolled as well — ``maya`` prepares the reconciliations of J-13. Named, not derived from a
# permission: the world says who signs off.
SIGN_OFF_PERSONAS: Final = frozenset({"maya"})


def needs_mfa(persona: Persona, group: TenantGroup) -> bool:
    """WLD-U-R2: the persona holds a ``requires_mfa`` permission in the group's tenants, or its
    journey signs off (``SIGN_OFF_PERSONAS``)."""
    return persona.key in SIGN_OFF_PERSONAS or any(
        spec(permission).requires_mfa
        for code in persona.roles_in(group)
        for permission in role_permissions(code)
    )


def validate_personas(personas: Sequence[Persona]) -> None:
    """Refuse the cast before any write: an email outside ``demo.erev`` (WLD-R-04), a repeated
    persona, an unknown role code, or a cast without the admin and the role approver."""
    keys: set[str] = set()
    for persona in personas:
        match = _EMAIL.fullmatch(persona.email.lower())
        if match is None or match.group(1) != DEMO_DOMAIN:
            raise SeedRefused(
                f"Refusing to seed persona {persona.wld_id}: its email is outside {DEMO_DOMAIN}"
            )
        if persona.key in keys:
            raise SeedRefused(f"Refusing to seed persona {persona.wld_id}: it is listed twice")
        keys.add(persona.key)
        for codes in persona.roles.values():
            for code in codes:
                if code not in DEFAULT_ROLES and code not in CUSTOM_ROLES:
                    raise SeedRefused(
                        f"Refusing to seed persona {persona.wld_id}: role {code} is unknown"
                    )
    for required in (ADMIN, ROLE_APPROVER):
        if required not in keys:
            raise SeedRefused(f"Refusing to seed: the cast has no persona {required}")
