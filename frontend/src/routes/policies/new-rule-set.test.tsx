// @vitest-environment jsdom
// SF-13 "New rule set" (SCREENS §11.1; 04 API-R-25 `POST /rule-sets`, `POST /rule-sets/{id}/versions`):
// one press creates the rule set and its first draft version. DG-FE-05 rev 1.156 (item W-23): when the
// second command gets no answer, the second press sends both under the keys they had, so the API
// replays the rule set it created instead of refusing a second one with the same code.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { RuleSet, RuleSetVersion } from "../../lib/api/queries/rule-sets";
import { installMemoryStorage, renderWithApp, signedInMe } from "../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import { NewRuleSetDrawer } from "./revenue";

installMswServer();
installMemoryStorage();

afterEach(() => {
  cleanup();
});

const RULE_SET_ID = "6f1c2a3b-4d5e-4f60-8a1b-2c3d4e5f6a7b";
const VERSION_ID = "7a2b3c4d-5e6f-4a70-9b1c-2d3e4f5a6b7c";

const RULE_SET: RuleSet = {
  id: RULE_SET_ID,
  code: "HOLD-2026",
  name: "HOLD-2026",
  kind: "HOLD",
  description: null,
  current_version: null,
  latest_version: null,
  created_at: "2026-09-01T12:00:00Z",
  updated_at: "2026-09-01T12:00:00Z",
  row_version: 1,
};

const VERSION: RuleSetVersion = {
  id: VERSION_ID,
  rule_set_id: RULE_SET_ID,
  rule_set_code: "HOLD-2026",
  kind: "HOLD",
  version_no: 1,
  status: "DRAFT",
  effective_from: null,
  effective_to: null,
  content_sha256: null,
  approval_request_id: null,
  pending_approval_request_id: null,
  published_at: null,
  published_by: null,
  supersedes_version_id: null,
  rule_count: 0,
  lint_result: null,
  test_evidence: { total: 0, passed: 0, failed: 0, not_run: 0, last_run_at: null },
  impact_simulation: null,
  created_at: "2026-09-01T12:00:00Z",
  updated_at: "2026-09-01T12:00:00Z",
  row_version: 1,
};

describe("SF-13 New rule set", () => {
  it("the version gets no answer: the second press sends the rule set and its version under the keys they had", async () => {
    const sent: { readonly path: string; readonly key: string | null; readonly body: unknown }[] =
      [];
    let lose = true;
    server.use(
      http.get(apiUrl("/api/v1/me/notifications"), () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.post(apiUrl("/api/v1/rule-sets"), async ({ request }) => {
        sent.push({
          path: "/api/v1/rule-sets",
          key: request.headers.get("Idempotency-Key"),
          body: await request.json(),
        });
        // What the API answers to the first send, and replays to the second under the same key.
        return HttpResponse.json(RULE_SET, { status: 201 });
      }),
      http.post(apiUrl(`/api/v1/rule-sets/${RULE_SET_ID}/versions`), async ({ request }) => {
        sent.push({
          path: `/api/v1/rule-sets/${RULE_SET_ID}/versions`,
          key: request.headers.get("Idempotency-Key"),
          body: await request.json(),
        });
        if (lose) {
          lose = false;
          return HttpResponse.error();
        }
        return HttpResponse.json(VERSION, { status: 201 });
      }),
    );
    const onClose = vi.fn();
    renderWithApp(<NewRuleSetDrawer kinds={["HOLD"]} onClose={onClose} />, {
      entry: "/policies/revenue",
      me: signedInMe({ permissions: ["config.read", "config.author"] }),
    });

    const drawer = await screen.findByRole("dialog", { name: "New rule set" });
    fireEvent.change(screen.getByRole("textbox", { name: /^Code/ }), {
      target: { value: "HOLD-2026" },
    });
    const press = screen.getByRole("button", { name: "Create rule set" });
    fireEvent.click(press);

    // First press: the rule set exists, the version's answer is lost. The drawer says so, stays open
    // and keeps its input.
    expect(await screen.findByText("No answer came back from the server. Try again.")).toBeTruthy();
    expect(onClose).not.toHaveBeenCalled();
    expect(drawer.isConnected).toBe(true);
    await waitFor(() => {
      expect(press.getAttribute("aria-busy")).not.toBe("true");
    });

    fireEvent.click(press);
    expect(await screen.findByText("Created rule set HOLD-2026.")).toBeTruthy();
    expect(onClose).toHaveBeenCalledTimes(1);
    expect(sent.map((item) => item.path)).toEqual([
      "/api/v1/rule-sets",
      `/api/v1/rule-sets/${RULE_SET_ID}/versions`,
      "/api/v1/rule-sets",
      `/api/v1/rule-sets/${RULE_SET_ID}/versions`,
    ]);
    // Second press: the rule set under its old key with the same body (a new key would be refused:
    // the code exists), and the version under its old key for that rule set.
    expect(sent[0]?.key).toMatch(/^[0-9a-f-]{36}$/);
    expect(sent[2]?.key).toBe(sent[0]?.key);
    expect(sent[2]?.body).toEqual(sent[0]?.body);
    expect(sent[3]?.key).toBe(sent[1]?.key);
    expect(sent[1]?.key).not.toBe(sent[0]?.key);
  });

  // SCREENS §0.7 SCR-ST-13, DG-FE-06 rev 1.228 (item KIT-UNPLACED-ERRORS-1): the drawer showed its
  // banner only while the problem carried no field errors at all, so a refusal that named a member
  // the drawer has no field for was shown nowhere.
  it("a refusal of New rule set says in the banner what no field of the drawer shows", async () => {
    server.use(
      http.get(apiUrl("/api/v1/me/notifications"), () =>
        HttpResponse.json({ items: [], next_cursor: null }),
      ),
      http.post(apiUrl("/api/v1/rule-sets"), () =>
        problemResponse("validation-failed", 422, "Check the highlighted fields", {
          errors: [
            {
              field: "code",
              sheet: null,
              row: null,
              rule_id: null,
              message: "Use letters, digits and hyphens.",
            },
            {
              field: "scope",
              sheet: null,
              row: null,
              rule_id: null,
              message: "A hold rule set names the entities it holds for.",
            },
          ],
        }),
      ),
    );
    renderWithApp(<NewRuleSetDrawer kinds={["HOLD"]} onClose={vi.fn()} />, {
      entry: "/policies/revenue",
      me: signedInMe({ permissions: ["config.read", "config.author"] }),
    });

    const dialog = await screen.findByRole("dialog", { name: "New rule set" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Code/ }), {
      target: { value: "HOLD 2026" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create rule set" }));

    const banner = await within(dialog).findByRole("alert");
    expect(
      within(banner).getByText("A hold rule set names the entities it holds for."),
    ).toBeTruthy();
    expect(within(banner).queryByText("Use letters, digits and hyphens.")).toBeNull();
    expect(within(dialog).getAllByText("Use letters, digits and hyphens.")).toHaveLength(1);
  });
});
