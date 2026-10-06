// MFA enrolment gate (03 REQ-PLT-005; docs/dev-guide.md DG-FE-02; SCREENS RT-03). A user who must
// enrol reaches only `/mfa/enrol` until enrolment succeeds: every other authenticated path redirects
// there. Public routes sit outside the session branch and are not gated. The step comes from the
// session (`mfa_enrolment_required`, on `GET /session` too), and the API enforces it: until the
// factor is confirmed it answers the session read, sign-out and the enrolment routes only.
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router";

export const MFA_ENROL_PATH = "/mfa/enrol";

export interface MfaGateProps {
  readonly enrolmentRequired: boolean;
  readonly children: ReactNode;
}

export function MfaGate({ enrolmentRequired, children }: MfaGateProps) {
  const { pathname } = useLocation();
  const onEnrolment = pathname.replace(/\/+$/, "") === MFA_ENROL_PATH;
  if (enrolmentRequired && !onEnrolment) {
    return <Navigate replace to={MFA_ENROL_PATH} />;
  }
  return children;
}
