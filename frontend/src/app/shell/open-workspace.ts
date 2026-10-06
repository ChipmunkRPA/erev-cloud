// The workspace a session is in, as `GET /me` lists it (04 API-R-01 `GET /session` `active_tenant`,
// API-R-03 `GET /me` memberships; SCREENS_B §9.7 "The open workspace"; 05 SBX-03). `GET /me`
// `active_membership_id` does not name it: a sandbox copy keeps the ids of the rows it copies, so the
// member of a workspace and of its copies holds memberships with ONE `membership_id`. A user has one
// membership in a workspace and the session names the workspace, so a membership is the open one when
// its workspace is the session's. Every reader of "the open workspace" goes through this module.
import { type Me, type MeMembership, useMe } from "../../lib/api/queries/me";
import type { SessionState } from "../auth/RequireSession";
import { useShellSession } from "./SandboxIndicator";

/** The id of the workspace the session is in; null without a session or without a workspace. */
export function openTenantId(session: SessionState | undefined): string | null {
  if (session?.authenticated !== true) {
    return null;
  }
  return session.active_tenant?.id ?? null;
}

/** The membership of the workspace the session is in; null while `GET /me` lists none for it. */
export function openMembership(
  me: Pick<Me, "memberships"> | undefined,
  session: SessionState | undefined,
): MeMembership | null {
  const tenantId = openTenantId(session);
  if (me === undefined || tenantId === null) {
    return null;
  }
  return me.memberships.find((membership) => membership.tenant.id === tenantId) ?? null;
}

/** `openMembership` of the cached `GET /me` and `GET /session`. */
export function useOpenMembership(): MeMembership | null {
  return openMembership(useMe().data, useShellSession());
}
