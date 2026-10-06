// @vitest-environment jsdom
// The open workspace (SCREENS_B §9.7 "The open workspace"; 04 API-R-01 `GET /session`, API-R-03 `GET
// /me`): a sandbox copy keeps the ids of the rows it copies, so the member of a workspace and of its
// copies holds one membership id in all of them; the session names the workspace that is open.
import { describe, expect, it } from "vitest";

import { signedInMe, signedInSession } from "../../test/app";
import { openMembership, openTenantId } from "./open-workspace";

const COPY_ID = "1c1c1c1c-1c1c-4c1c-8c1c-1c1c1c1c1c1c";

function memberOfACopy() {
  const base = signedInMe();
  const source = base.memberships[0];
  if (source === undefined) {
    throw new Error("no membership");
  }
  const copy = {
    ...source,
    tenant: {
      ...source.tenant,
      id: COPY_ID,
      code: "sbx-avenmoor-rehearsal",
      display_name: "Avenmoor rehearsal",
      kind: "sandbox" as const,
      source_tenant_id: source.tenant.id,
      source_known_at: "2026-09-12T18:10:00Z",
    },
  };
  return { me: { ...base, memberships: [source, copy] }, source, copy };
}

const IN_COPY = signedInSession({
  active_tenant: {
    id: COPY_ID,
    code: "sbx-avenmoor-rehearsal",
    display_name: "Avenmoor rehearsal",
    kind: "sandbox",
  },
});

describe("the open workspace", () => {
  it("is the session's: of two memberships with one id, the one whose workspace the session is in", () => {
    const { me, source, copy } = memberOfACopy();
    expect(copy.membership_id).toBe(source.membership_id);
    // `active_membership_id` names both and so neither.
    expect(
      me.memberships.filter((membership) => membership.membership_id === me.active_membership_id),
    ).toHaveLength(2);
    expect(openMembership(me, signedInSession())).toBe(source);
    expect(openMembership(me, IN_COPY)).toBe(copy);
    expect(openTenantId(IN_COPY)).toBe(COPY_ID);
  });

  it("is none without a session, without a workspace, before GET /me, or when GET /me lists no membership of it", () => {
    const { me, source } = memberOfACopy();
    expect(openTenantId(undefined)).toBeNull();
    expect(
      openTenantId({ authenticated: false, capabilities: { identity_providers: [] } }),
    ).toBeNull();
    expect(openTenantId(signedInSession({ active_tenant: null }))).toBeNull();
    expect(openMembership(me, undefined)).toBeNull();
    expect(openMembership(me, signedInSession({ active_tenant: null }))).toBeNull();
    expect(openMembership(undefined, IN_COPY)).toBeNull();
    expect(openMembership({ memberships: [source] }, IN_COPY)).toBeNull();
  });
});
