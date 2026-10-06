// @vitest-environment jsdom
// The landing of a workspace that is being set up (SCREENS_B §11.1; PRD BR-PLT-02; SCREENS §0.6
// SCR-PERM-02 (c); item W-12e): a member who holds settings.manage lands on SF-15:setup while
// `setup_completed_at` is null. `GET /tenant` answers a holder for all entities alone (04 API-C-03), so
// the read is sent only by such a member; a holder for one entity lands on the landing route and asks
// for nothing.
import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";

import { queryKeys } from "../lib/api/query-keys";
import { signedInMe, signedInSession } from "../test/app";
import { apiUrl, installMswServer, server } from "../test/msw";
import { createQueryClient } from "./providers";
import { landingTarget, SETUP_LANDING_PATH } from "./router";

installMswServer();

const ENTITY = "0a1b2c3d-4e5f-4a6b-8c7d-0000000000de";
const BUILT = new Set([SETUP_LANDING_PATH, "/home"]);

function clientOf(me: ReturnType<typeof signedInMe>) {
  const client = createQueryClient();
  client.setQueryData(queryKeys.session(), signedInSession());
  client.setQueryData(queryKeys.me(), me);
  return client;
}

describe("the landing while the workspace is being set up", () => {
  it("asks for the tenant only when settings.manage is held for all entities", async () => {
    let reads = 0;
    server.use(
      http.get(apiUrl("/api/v1/tenant"), () => {
        reads += 1;
        return HttpResponse.json({
          id: "0b6f3e2d-1c4a-4b8e-9d7f-6a5c4b3e2d1f",
          code: "avenmoor",
          display_name: "Avenmoor",
          kind: "production",
          setup_completed_at: null,
        });
      }),
    );

    const one = signedInMe({
      permissions: ["settings.manage"],
      permission_scopes: { "settings.manage": [ENTITY] },
    });
    expect(await landingTarget(clientOf(one), BUILT, "/home")).toBe("/home");
    expect(reads).toBe(0);

    const all = signedInMe({ permissions: ["settings.manage"] });
    expect(await landingTarget(clientOf(all), BUILT, "/home")).toBe(SETUP_LANDING_PATH);
    expect(reads).toBe(1);
  });
});
