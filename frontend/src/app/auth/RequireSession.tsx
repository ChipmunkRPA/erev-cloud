// Session guard (docs/dev-guide.md DG-FE-02; SCREENS SCR-URL-30; 04 API-S-Session; 03 REQ-PLT-005). The
// loader of the authenticated branch reads the session through the query cache, where sign-in stores
// its response, else `GET /session`, and sends a visitor without a session to `/sign-in?next=<path>`.
// The element keeps reading the cached session, so a session that ends later leaves the branch as
// well. A session that still owes its second factor reaches no screen of the branch: the challenge
// goes to SF-22:mfa-challenge with the path the visitor asked for, the enrolment step to MfaGate.
// The server refuses such a session on every other route; this guard only saves the refused calls.
import { type QueryClient, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import {
  data,
  type LoaderFunctionArgs,
  Navigate,
  Outlet,
  redirect,
  useLoaderData,
  useLocation,
} from "react-router";

import { api, setSecondFactorListener, SIGN_IN_PATH, unwrap } from "../../lib/api/client";
import { queryKeys } from "../../lib/api/query-keys";
import type { components } from "../../lib/api/schema";
import { MfaGate } from "./MfaGate";

type AnonymousSessionOut = components["schemas"]["AnonymousSessionOut"];

/**
 * A valid session (04 API-S-Session). `mfa_required` and `mfa_enrolment_required` state the
 * second-factor step the session still owes, on the sign-in answers and on `GET /session` alike, so
 * a reload reads the same step.
 */
export type Session = components["schemas"]["SessionOut"];
export type SessionState = Session | AnonymousSessionOut;

export const SESSION_ROUTE_ID = "X:session";
/** RT-02 SF-22:mfa-challenge, where a session that owes the challenge answers it. */
export const MFA_CHALLENGE_PATH = "/sign-in/mfa";

/** SF-22:mfa-challenge with `next` = the same-origin path and search the visitor asked for. */
export function challengePath(next: string): string {
  return `${MFA_CHALLENGE_PATH}?${new URLSearchParams({ next }).toString()}`;
}

export function fetchSession(): Promise<SessionState> {
  return unwrap(api.GET("/api/v1/session"));
}

/** SCREENS SCR-URL-30: sign-in with `next` = the same-origin path and search the visitor asked for. */
export function signInPath(next: string): string {
  return `${SIGN_IN_PATH}?${new URLSearchParams({ next }).toString()}`;
}

/** The loader of X:session: the cached session, else `GET /session`; no session redirects. */
export function sessionLoader(queryClient: QueryClient) {
  return async ({ request }: LoaderFunctionArgs): Promise<Session> => {
    const session = await queryClient.ensureQueryData({
      queryKey: queryKeys.session(),
      queryFn: fetchSession,
    });
    if (!session.authenticated) {
      const { pathname, search } = new URL(request.url);
      if (pathname.replace(/\/+$/, "") === SIGN_IN_PATH) {
        // Sign-in never redirects to itself (as lib/api/client.ts): a sign-in path that reaches
        // this branch has no public route, so it is not found.
        throw data(null, { status: 404 });
      }
      throw redirect(signInPath(`${pathname}${search}`));
    }
    return session;
  };
}

/** The first session read shows the canvas only; there is no blocking spinner (DS-AP-09). */
export function SessionPending() {
  return <div aria-busy="true" className="h-dvh bg-canvas" />;
}

export function RequireSession() {
  const loaded = useLoaderData() as Session;
  const { pathname, search } = useLocation();
  const queryClient = useQueryClient();
  const { data: session } = useQuery({
    queryKey: queryKeys.session(),
    queryFn: fetchSession,
    initialData: loaded,
  });
  // A step that became due after the session was read (a role granted meanwhile, a factor
  // enrolled elsewhere) shows as a refused call: the session is read again and the guard routes on.
  useEffect(() => {
    setSecondFactorListener(() => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.session() });
    });
    return () => {
      setSecondFactorListener(null);
    };
  }, [queryClient]);
  if (!session.authenticated) {
    return <Navigate replace to={signInPath(`${pathname}${search}`)} />;
  }
  if (session.mfa_required) {
    return <Navigate replace to={challengePath(`${pathname}${search}`)} />;
  }
  return (
    <MfaGate enrolmentRequired={session.mfa_enrolment_required}>
      <Outlet />
    </MfaGate>
  );
}
