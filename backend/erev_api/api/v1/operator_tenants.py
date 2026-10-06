"""API-R-54 Operator tenant provisioning (04 §15.3 API-R-54, §14.3; dev-guide §5.20 DG-KRN-TEN-05,
DG-KRN-TEN-06; 03 REQ-PLT-038; PRD BR-PLT-01; 05 SAR-24; BUILD_SPEC PLF-29).

``POST /operator/tenants`` runs ``tenant.provision`` for an MFA-verified platform operator. There is
no tenant context and no tenant permission, so the route is guarded by ``require_operator`` instead
of ``command``: the ``Idempotency-Key`` is validated, but no ``idempotency_record`` is written,
and a repeated request fails with ``TENANT_CODE_EXISTS``. API-R-54 has no read route, so the 201
carries no ``Location``.
"""

from __future__ import annotations

from typing import Annotated, Final
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response
from pydantic import AwareDatetime, BaseModel, ConfigDict

from erev_api.api.deps import (
    API_PREFIX,
    IDEMPOTENCY_KEY_OPERATOR_REF,
    GuardedRoute,
    problem_responses,
    validate_idempotency_key,
)
from erev_api.auth.dependencies import request_facts, require_operator
from erev_api.auth.principal import OperatorContext
from erev_api.auth.ratelimit import LoginRateLimiter
from erev_api.clock import Clock, get_clock
from erev_api.domain.platform.provisioning import (
    InvitationReissue,
    OperatorActor,
    TenantProvisionRequest,
    TenantProvisionResult,
    provision_tenant,
)
from erev_api.enums import TenantKind
from erev_api.money import CurrencyCode
from erev_api.problems import Problem

TAG: Final = "API-R-54 Operator tenant provisioning"
OPERATOR_EXTENSION: Final = "x-erev-operator"
# [J] SPEC-Q-194: copy of the per-address refusal.
PROVISION_RETRY: Final = "Too many workspace requests. Try again in {seconds} seconds."

router = APIRouter(prefix=API_PREFIX, tags=[TAG], route_class=GuardedRoute)


class OperatorTenantCreateIn(BaseModel):
    """``POST /operator/tenants``: the ``erev tenant create`` fields."""

    model_config = ConfigDict(extra="forbid")

    code: str
    display_name: str
    reporting_currency: CurrencyCode
    is_demo: bool = False
    admin_email: str
    industry_cluster: str | None = None  # T-PLT-01; perf:<16 hex> for the PRF-2 volume tenant


class OperatorTenantSummaryOut(BaseModel):
    id: UUID
    code: str
    kind: TenantKind
    display_name: str
    reporting_currency: str
    is_demo: bool


class OperatorTenantOut(BaseModel):
    """The API-R-54 201 body; ``erev tenant create`` prints the same document."""

    tenant: OperatorTenantSummaryOut
    admin_membership_id: UUID
    invitation_expires_at: AwareDatetime

    @classmethod
    def of(cls, result: TenantProvisionResult) -> OperatorTenantOut:
        return cls(
            tenant=OperatorTenantSummaryOut.model_validate(dict(result.tenant)),
            admin_membership_id=result.admin_membership_id,
            invitation_expires_at=result.invitation_expires_at,
        )


class OperatorInvitationTenantOut(BaseModel):
    id: UUID
    code: str


class OperatorInvitationOut(BaseModel):
    """What ``erev tenant resend-invitation`` prints (04 §14.3 step 5, rev 1.114). No route
    returns it: issuing the first invitation again is a command-line repair."""

    tenant: OperatorInvitationTenantOut
    admin_membership_id: UUID
    invitation_expires_at: AwareDatetime

    @classmethod
    def of(cls, done: InvitationReissue) -> OperatorInvitationOut:
        return cls(
            tenant=OperatorInvitationTenantOut(id=done.tenant_id, code=done.tenant_code),
            admin_membership_id=done.admin_membership_id,
            invitation_expires_at=done.invitation_expires_at,
        )


@router.post(
    "/operator/tenants",
    operation_id="operator_tenants_create",
    status_code=201,
    response_model=OperatorTenantOut,
    responses=problem_responses(
        "unauthenticated",
        "session-expired",
        "forbidden",
        "mfa-required",
        "validation-failed",
        "rate-limited",
    ),
    # F-SNP-I51-DOC1: the header the route validates directly is declared through the shared
    # operator component (no tenant idempotency record, no stored-response replay).
    openapi_extra={OPERATOR_EXTENSION: True, "parameters": [dict(IDEMPOTENCY_KEY_OPERATOR_REF)]},
)
def create_tenant(
    body: OperatorTenantCreateIn,
    request: Request,
    op: Annotated[OperatorContext, Depends(require_operator())],
    clock: Annotated[Clock, Depends(get_clock)],
) -> Response:
    """Provision a production workspace with its seed and invite its Tenant Admin.

    A code already in use gives 422 ``validation-failed`` with ``rule_id`` ``TENANT_CODE_EXISTS``,
    and nothing is created.
    """
    validate_idempotency_key(request)
    limiter: LoginRateLimiter = request.app.state.operator_rate_limiter
    facts = request_facts(request, clock)
    retry_after = limiter.admit(address=facts.source_ip or "unknown", email=None, now=facts.now)
    if retry_after is not None:
        raise Problem(
            "rate-limited",
            PROVISION_RETRY.format(seconds=retry_after),
            headers={"Retry-After": str(retry_after)},
        )
    result = provision_tenant(
        TenantProvisionRequest(
            code=body.code,
            display_name=body.display_name,
            reporting_currency=body.reporting_currency,
            is_demo=body.is_demo,
            admin_email=body.admin_email,
            industry_cluster=body.industry_cluster,
        ),
        actor=OperatorActor(
            channel="API",
            operator_user_id=op.operator_user_id,
            os_user=None,
            request_id=op.request_id,
        ),
        clock=clock,
        keyring=request.app.state.keyring,
        key_provisioner=request.app.state.key_provisioner,
    )
    return JSONResponse(OperatorTenantOut.of(result).model_dump(mode="json"), status_code=201)
