"""Demo content builders registered in ``erev seed demo`` (BUILD_SPEC XR-09, RFD-16; PRD §2.1
WLD-R-01 to WLD-R-04; dev-guide DG-MK-seed).

``seed_demo`` provisions a demo tenant and signs its personas in; ``run`` then executes the builders
registered for the tenant's WLD id, in order. A builder receives a ``BuildContext`` and writes only
through domain commands executed as persona users: ``command`` opens a committed unit of work as the
persona behind the route guard of the command, and ``approve`` decides the pending approval request
of a subject as a persona other than its preparer (WLD-R-02). ``run`` refuses a tenant whose
``is_demo`` is false before any builder writes (WLD-R-04).

``with_close`` says that the seed was asked for the close of the demo world (``erev seed demo
--with-close``; ``demo.close_history``): the stage is a builder like the others and does nothing
without it. ``step_up`` lets a persona verify her second factor again before a command that asks
for a verification at most five minutes old (BR-PLT-06).
"""

from __future__ import annotations

from collections.abc import Callable, Iterator, Mapping, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Final
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from erev_api.approvals import engine as approvals
from erev_api.auth.keyring import KeyRing
from erev_api.auth.principal import RequestContext
from erev_api.clock import Clock
from erev_api.db.session import DbContext, tenant_session
from erev_api.db.tables import approval_request, tenant
from erev_api.domain.demo import SeedRefused, close_history
from erev_api.domain.demo.avenmoor import background as avenmoor_background
from erev_api.domain.demo.avenmoor import contracts as avenmoor_contracts
from erev_api.domain.demo.avenmoor import imports as avenmoor_imports
from erev_api.domain.demo.avenmoor import policies as avenmoor_policies
from erev_api.domain.demo.avenmoor import reference as avenmoor_reference
from erev_api.domain.demo.avenmoor import ssp as avenmoor_ssp
from erev_api.domain.demo.industry import reference as industry_reference
from erev_api.domain.demo.personas import Persona
from erev_api.enums import ApprovalRequestStatus, ApprovalSubjectType
from erev_api.files.store import FileStore
from erev_api.uow import UnitOfWork, unit_of_work

APPROVAL_COMMENT: Final = "Reviewed for the demo world."
MAX_DECISIONS: Final = 10  # [J] a routed request has at most ten steps (T-PLT-18)


@dataclass(frozen=True, slots=True)
class BuildContext:
    """What a builder may use: the tenant, the signed-in cast and the command services."""

    tenant_id: UUID
    tenant_code: str
    wld_id: str
    cast: Mapping[str, Persona]  # by persona key
    clock: Clock
    keyring: KeyRing
    files: FileStore
    request_id: str
    principal_context: Callable[[Persona, UUID], RequestContext]
    guard: Callable[[RequestContext, str], None]
    # The seed was asked for the close (``--with-close``): the builders that hold open-period
    # items leave them for the stage (``close_history``).
    with_close: bool = False
    # How a persona verifies again when her verification is stale (``PersonaRun.step_up``); a
    # caller whose clock stands still passes none.
    verify_again: Callable[[Persona], None] | None = None

    def context(self, persona: str) -> RequestContext:
        return self.principal_context(self.cast[persona], self.tenant_id)

    def step_up(self, persona: str) -> None:
        """Before a command that asks for a fresh second-factor verification (BR-PLT-06): the
        persona verifies again when hers is older than the window."""
        if self.verify_again is not None:
            self.verify_again(self.cast[persona])

    @contextmanager
    def command(self, persona: str, permission: str | None = None) -> Iterator[UnitOfWork]:
        """A unit of work as ``persona``, committed when the block ends without an exception.
        ``permission`` is the route guard of the command (``Depends(command(<permission>))``);
        commands guarded inside the domain pass None."""
        ctx = self.context(persona)
        if permission is not None:
            self.guard(ctx, permission)
        with unit_of_work(ctx, clock=self.clock, keyring=self.keyring, files=self.files) as uow:
            yield uow
            uow.commit()

    @contextmanager
    def read(self) -> Iterator[Session]:
        """A read-only tenant session over every entity."""
        scope = DbContext(tenant_id=self.tenant_id, user_id=None, entity_scope="*")
        with tenant_session(scope, read_only=True) as session:
            yield session

    def approve(
        self, subject_type: ApprovalSubjectType, subject_id: UUID, approvers: Sequence[str]
    ) -> UUID:
        """Approve the subject's pending request, one decision per routed step, each by the next
        persona of ``approvers`` (``POST /approvals/{id}/approve`` with the hashes the request
        shows). Returns the request id; ``LookupError`` when no request is pending or it does not
        end APPROVED."""
        request_id: UUID | None = None
        for decision in range(MAX_DECISIONS):
            with self.read() as session:
                pending = session.execute(
                    select(
                        approval_request.c.id,
                        approval_request.c.subject_content_sha256,
                        approval_request.c.impact_preview_sha256,
                    ).where(
                        approval_request.c.subject_type == subject_type.value,
                        approval_request.c.subject_id == subject_id,
                        approval_request.c.status == ApprovalRequestStatus.PENDING.value,
                    )
                ).one_or_none()
            if pending is None:
                break
            request_id = UUID(str(pending.id))
            approver = approvers[min(decision, len(approvers) - 1)]
            with self.command(approver) as uow:
                approvals.decide(
                    uow,
                    approval_request_id=request_id,
                    decision="APPROVE",
                    subject_content_sha256=str(pending.subject_content_sha256),
                    impact_preview_sha256=pending.impact_preview_sha256,
                    comment=APPROVAL_COMMENT,
                    reason_code=None,
                )
        if request_id is None:
            raise LookupError(f"{subject_type.value} {subject_id} has no pending approval request")
        with self.read() as session:
            status = session.execute(
                select(approval_request.c.status).where(approval_request.c.id == request_id)
            ).scalar_one()
        if str(status) != ApprovalRequestStatus.APPROVED.value:
            raise LookupError(f"approval request {request_id} ended {status}")
        return request_id


type Builder = Callable[[BuildContext], None]

# WLD id → builders in execution order. The Avenmoor policies builder runs before the contract
# builders (CTR-20): its published APPROVAL_ROUTING and AUTO_APPROVAL rule sets route every later
# request (PRD §2.5).
BUILDERS: Final[Mapping[str, tuple[Builder, ...]]] = {
    "WLD-T-01": (
        avenmoor_reference.build,
        avenmoor_ssp.build,
        avenmoor_policies.build,
        avenmoor_contracts.build,
        avenmoor_background.build,
        # CLO-22: the close of AVM-US and, after it, the open-period items of the background
        # contracts — only for a seed asked ``--with-close``; otherwise nothing.
        close_history.build,
        avenmoor_imports.build,  # WLD-B-04 on the background contracts (DIN-15)
    ),
    # RFD-17: the industry tenants' structure, chart and mapping, Riverbend's engine billing policy
    # and the cluster's DRAFT industry templates (BS3-D-10).
    **{wld_id: (industry_reference.build,) for wld_id in industry_reference.BY_WLD},
}


def builders_for(wld_id: str) -> tuple[Builder, ...]:
    return BUILDERS.get(wld_id, ())


def refuse_non_demo(ctx: BuildContext) -> None:
    """WLD-R-04: ``SeedRefused`` unless the tenant exists with ``is_demo`` true."""
    with ctx.read() as session:
        is_demo = session.execute(
            select(tenant.c.is_demo).where(tenant.c.id == ctx.tenant_id)
        ).scalar_one_or_none()
    if is_demo is not True:
        raise SeedRefused(f"Refusing to seed {ctx.tenant_code}: is_demo is false")


def run(ctx: BuildContext) -> None:
    """Run the builders of the tenant's WLD id after the WLD-R-04 check; a ``Problem`` from a
    command propagates."""
    builders = builders_for(ctx.wld_id)
    if not builders:
        return
    refuse_non_demo(ctx)
    for builder in builders:
        builder(ctx)
