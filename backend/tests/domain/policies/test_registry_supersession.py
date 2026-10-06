"""PRODUCT DEFECT witness, RED until its owner repairs it — a later registry version drops the
values an earlier version of the same category and scope key stated (04 T-PLT-32; POLICIES §0.5
rule 2; dev-guide DG-KRN-REG-01). Written by lane F-SNP on the supervisor's order of 2026-09-30
(item CFG-PLATFORM-PIN-1, the lane's addendum): measure, do not fix; the supervisor rules the owner.

What happens. A registry version holds ``values`` for one category at one scope key and is stored
as it is sent (``registry.presets.create_draft_version``). Publication supersedes the prior
PUBLISHED version of the key at the new version's effective instant without merging
(``policies.lifecycle``), and ``registry.resolve`` consults only the newest version in force at a
level: a parameter that version does not hold passes to the next level, in the end to the
framework default — never to the superseded version. So a value stays in force only while every
later version of its category restates it.

Who restates. SF-13:accounting offers "Start from the current published values", ticked by
default, and then sends the whole set (``frontend/src/routes/policies/accounting.tsx``).
SF-15:workspace sends one version per changed category "with the changed values only"
(``frontend/src/routes/settings/workspace.tsx``). The API accepts a partial set without a word.

Measured through the product's commands — draft, test, submit by Maya, approval by Marcus —
on 2026-09-30 (main 5d736130), the frozen clock at 12 Sep 2026:

* PLATFORM, TENANT: v2 ``platform.job_concurrency`` 8 from 1 Oct, v3 the five snapshot retention
  families from 1 Nov, v4 ``platform.audit_retention_years`` 10 from 1 Dec. On 15 Oct the
  concurrency resolves 8 at TENANT; on 15 Nov it resolves 4 at FRAMEWORK_DEFAULT and the retention
  is confirmed; on 15 Dec the retention is unset again (``snapshot_job.retention_policy_for``
  answers the refusing default, so no snapshot and no sandbox copy can be taken), the audit
  retention resolves 10 and the concurrency 4.
* PRACTICAL_EXPEDIENT, ENTITY AVM-US: v1 ``costs.obtain_expedient`` DO_NOT_APPLY from 1 Oct, v2
  ``sfc.one_year_expedient`` DO_NOT_APPLY from 1 Nov. On 15 Oct the first resolves DO_NOT_APPLY at
  ENTITY; on 15 Nov it resolves APPLY at FRAMEWORK_DEFAULT. It is the registry's rule, not one
  category's.

Each test states what a person who approved the earlier version expects — the value stands until
a later version states another value for that parameter — and compares it with what resolves, all
instants in one assertion so that the failure shows every figure. If the ruling keeps whole-set
versions instead (a version must restate what it keeps), these expectations change with it: a
version that omits a value the published version of its key states is then refused, or restated
by the screen, and the witness moves to that rule.

Also measured, not asserted here: the request sequence of SF-15:workspace — ``POST /policies``
without ``effective_from``, ``POST /test``, ``POST /submit`` — ends at the submit with 422
``validation-failed`` on ``effective_from`` ("Choose the date this version takes effect."), so the
screen cannot submit a registry value at all today; and no screen sets
``platform.snapshot_retention_families`` (item SBX-RETENTION-UI-1).

Repaired by items REG-VERSION-WHOLE-SET-1 and CFG-PLATFORM-PIN-1 (supervisor ruling R-117 (b); 04
T-PLT-32 "Whole value set" and §16.5, rev 1.183): the server makes a version whole at its submit,
so both tests are green as they were written, no assertion moved, and the screen's request
sequence ends published. ``test_registry_whole_set`` holds the rule.
"""

from __future__ import annotations

from datetime import UTC, datetime

from erev_api.db.session import tenant_session
from erev_api.domain.platform import snapshot_dataset as sd
from erev_api.domain.platform import snapshot_job
from test_registry_versions import (  # noqa: F401  (``world`` is the fixture of that module)
    World,
    context,
    kernel,
    published,
    world,
)

# The first day of the month in New York and in Berlin (the pin rule of a period-scoped version).
OCTOBER = "2026-10-01T04:00:00Z"
NOVEMBER = "2026-11-01T04:00:00Z"
DECEMBER = "2026-12-01T05:00:00Z"
MID_OCTOBER = datetime(2026, 10, 15, 12, tzinfo=UTC)
MID_NOVEMBER = datetime(2026, 11, 15, 12, tzinfo=UTC)
MID_DECEMBER = datetime(2026, 12, 15, 12, tzinfo=UTC)
CONCURRENCY = "platform.job_concurrency"
AUDIT_YEARS = "platform.audit_retention_years"
OBTAIN = "costs.obtain_expedient"
ONE_YEAR = "sfc.one_year_expedient"


def _retention(found: World, known_at: datetime) -> str:
    """What the snapshot export reads at ``known_at``: a confirmed policy or the refusal."""
    with tenant_session(context(found.tenant_id), read_only=True) as session:
        resolution = snapshot_job.retention_policy_for(session, known_at)
    if resolution.policy is not None:
        return "confirmed"
    return "unset" if resolution.refusal is None else "unconfirmed"


def test_a_later_platform_version_keeps_the_values_it_does_not_state(world: World) -> None:  # noqa: F811
    """Three approved PLATFORM versions with disjoint keys. Expected: each value in force from its
    version's effective instant on. Measured red on 2026-09-30: the concurrency back at the
    default from 1 Nov, the retention confirmation gone from 1 Dec (module docstring)."""
    published(
        world, category="PLATFORM", scope="TENANT", values={CONCURRENCY: 8}, effective_from=OCTOBER
    )
    published(
        world,
        category="PLATFORM",
        scope="TENANT",
        values={sd.RETENTION_PARAMETER: dict(sd.RETENTION_FAMILIES)},
        effective_from=NOVEMBER,
    )
    published(
        world,
        category="PLATFORM",
        scope="TENANT",
        values={AUDIT_YEARS: 10},
        effective_from=DECEMBER,
    )
    measured = {
        "15 Oct concurrency": kernel(world, CONCURRENCY, known_at=MID_OCTOBER),
        "15 Nov concurrency": kernel(world, CONCURRENCY, known_at=MID_NOVEMBER),
        "15 Nov retention": _retention(world, MID_NOVEMBER),
        "15 Dec concurrency": kernel(world, CONCURRENCY, known_at=MID_DECEMBER),
        "15 Dec retention": _retention(world, MID_DECEMBER),
        "15 Dec audit years": kernel(world, AUDIT_YEARS, known_at=MID_DECEMBER),
    }
    assert measured == {
        "15 Oct concurrency": (8, "TENANT"),
        "15 Nov concurrency": (8, "TENANT"),  # an API version with only the retention families
        "15 Nov retention": "confirmed",
        "15 Dec concurrency": (8, "TENANT"),
        "15 Dec retention": "confirmed",  # a later version that changes another platform value
        "15 Dec audit years": (10, "TENANT"),
    }


def test_a_later_accounting_version_keeps_the_values_it_does_not_state(world: World) -> None:  # noqa: F811
    """The same in an accounting category: two approved PRACTICAL_EXPEDIENT versions of AVM-US with
    disjoint keys. Measured red on 2026-09-30: the first election back at the framework default
    from the second version's effective instant."""
    for values, effective_from in (
        ({OBTAIN: "DO_NOT_APPLY"}, OCTOBER),
        ({ONE_YEAR: "DO_NOT_APPLY"}, NOVEMBER),
    ):
        published(
            world,
            category="PRACTICAL_EXPEDIENT",
            scope="ENTITY",
            entity_code="AVM-US",
            values=values,
            effective_from=effective_from,
        )
    measured = {
        "15 Oct obtain": kernel(world, OBTAIN, known_at=MID_OCTOBER, entity_id=world.us_id),
        "15 Nov obtain": kernel(world, OBTAIN, known_at=MID_NOVEMBER, entity_id=world.us_id),
        "15 Nov one year": kernel(world, ONE_YEAR, known_at=MID_NOVEMBER, entity_id=world.us_id),
    }
    assert measured == {
        "15 Oct obtain": ("DO_NOT_APPLY", "ENTITY"),
        "15 Nov obtain": ("DO_NOT_APPLY", "ENTITY"),
        "15 Nov one year": ("DO_NOT_APPLY", "ENTITY"),
    }
