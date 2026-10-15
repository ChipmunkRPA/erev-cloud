// @vitest-environment jsdom
import { cleanup, screen, fireEvent, within, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeAll, expect, it } from "vitest";
import { SCREEN_ROUTES } from "../../app/router";
import { installMemoryStorage, preloadScreens, renderApp, signedInMe } from "../../test/app";
import { installGridViewport } from "../../test/layout";
import { apiUrl, installMswServer, server } from "../../test/msw";
import type { AIModelLog } from "../../lib/api/queries/ai-model-logs";

installMswServer();
installMemoryStorage();
installGridViewport();
afterEach(cleanup);
beforeAll(() => preloadScreens(SCREEN_ROUTES, ["SF-15:ai-call-log"]));
const id = "a4bfe1a2-cb18-4110-886e-fca643b828ac";
const record: AIModelLog = {
  id,
  provider: "fake",
  model_id: "fake-contract-review-v1",
  prompt_template_id: "contract-review",
  prompt_template_version: "1",
  parameters: { max_tokens: 4096, usage_evidence: "REPORTED" },
  input_sha256: "a".repeat(64),
  response_sha256: "b".repeat(64),
  usage_known: true,
  input_tokens: 1204,
  output_tokens: 388,
  latency_ms: 850,
  outcome: "SUCCESS",
  error_detail: null,
  created_at: "2026-10-15T10:00:00Z",
  created_by: { id, kind: "USER", display_name: "Maya" },
};
function serve(items: AIModelLog[] = [record]) {
  const calls: URL[] = [];
  server.use(
    http.get(apiUrl("/api/v1/saved-views"), ({ request }) => {
      expect(new URL(request.url).searchParams.get("screen_code")).toBe("SF-15:ai-call-log");
      return HttpResponse.json({ items: [], next_cursor: null });
    }),
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/entities"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/books"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/ai/model-logs"), ({ request }) => {
      calls.push(new URL(request.url));
      return HttpResponse.json(
        { items, next_cursor: null },
        { headers: { "X-Erev-Total-Count": String(items.length) } },
      );
    }),
    http.get(apiUrl("/api/v1/ai/model-logs/:id"), () => HttpResponse.json(record)),
  );
  return calls;
}
function renderLog(permissions = ["ai.use"], suffix = "") {
  const me = signedInMe({ permissions });
  server.use(http.get(apiUrl("/api/v1/me"), () => HttpResponse.json(me)));
  return renderApp("/settings/ai/call-log" + suffix, { me, screenRoutes: SCREEN_ROUTES });
}
it("renders call evidence and opens a freshly authorized detail drawer", async () => {
  const calls = serve();
  renderLog();
  const grid = await screen.findByRole("grid", { name: "AI calls" });
  expect(await within(grid).findByText("contract-review v1", {}, { timeout: 5000 })).toBeTruthy();
  expect(within(grid).getByText("Succeeded")).toBeTruthy();
  expect(calls[0]?.searchParams.get("limit")).toBe("50");
  expect(calls[0]?.searchParams.get("count")).toBe("true");
  fireEvent.click(within(grid).getByRole("link"));
  const drawer = await screen.findByTestId("SF-15-drawer-ai-call");
  expect(await within(drawer).findByText(record.input_sha256)).toBeTruthy();
  expect(within(drawer).getByText("usage_evidence")).toBeTruthy();
  expect(within(drawer).getByText("4096")).toBeTruthy();
});
it("opens bookmarked evidence even when it is absent from the current list page", async () => {
  serve([]);
  renderLog(["settings.manage"], `?drawer=call&call=${id}`);
  expect(await screen.findByText(record.input_sha256)).toBeTruthy();
  expect(await screen.findByText("No AI calls yet")).toBeTruthy();
});
it("does not request evidence without either permission", async () => {
  const calls = serve();
  renderLog(["contract.read"]);
  expect(await screen.findByRole("heading", { name: /You do not have access/ })).toBeTruthy();
  expect(calls).toHaveLength(0);
});
it("renders the documented empty state", async () => {
  serve([]);
  renderLog();
  expect(await screen.findByText("No AI calls yet")).toBeTruthy();
});

it("does not display unknown usage as zero in the grid or detail", async () => {
  const uncertain = {
    ...record,
    usage_known: false,
    input_tokens: 0,
    output_tokens: 0,
    outcome: "TIMEOUT" as const,
    response_sha256: null,
    parameters: { usage_evidence: "UNKNOWN" },
  };
  serve([uncertain]);
  server.use(http.get(apiUrl("/api/v1/ai/model-logs/:id"), () => HttpResponse.json(uncertain)));
  renderLog();
  const grid = await screen.findByRole("grid", { name: "AI calls" });
  expect(await within(grid).findAllByText("Unknown", {}, { timeout: 5000 })).toHaveLength(2);
  expect(within(grid).queryByText("0")).toBeNull();
  fireEvent.click(within(grid).getByRole("link"));
  expect(await screen.findByText("Token usage is unknown")).toBeTruthy();
  expect(within(screen.getByTestId("SF-15-drawer-ai-call")).queryByText("0")).toBeNull();
});
it("keeps confirmed zero usage visible", async () => {
  serve([{ ...record, input_tokens: 0, output_tokens: 0 }]);
  renderLog();
  const grid = await screen.findByRole("grid", { name: "AI calls" });
  expect(await within(grid).findAllByText("0", {}, { timeout: 5000 })).toHaveLength(2);
  expect(within(grid).queryByText("Unknown")).toBeNull();
});

it("restores a shared layout while keeping call reads under the current user's API", async () => {
  const calls = serve();
  server.use(
    http.get(apiUrl("/api/v1/saved-views"), () =>
      HttpResponse.json({
        items: [
          {
            id: "view-shared",
            membership_id: "other-member",
            screen_code: "SF-15:ai-call-log",
            name: "Review layout",
            is_shared: true,
            is_favourite: false,
            row_version: 1,
            created_at: "2026-10-15T10:00:00Z",
            updated_at: "2026-10-15T10:00:00Z",
            config: {
              columns: ["created_at", "template", "outcome"],
              sort: "created_at",
              filters: {},
              query: "",
              widths: {},
              pinned: { start: [], end: [] },
              currency_view: null,
            },
          },
        ],
        next_cursor: null,
      }),
    ),
  );
  const { router } = renderLog(["ai.use"], "?view=view-shared");
  const viewButton = await screen.findByRole("button", { name: "View: Review layout" });
  const grid = await screen.findByRole("grid", { name: "AI calls" });
  await waitFor(() =>
    expect(within(grid).queryByRole("columnheader", { name: "User" })).toBeNull(),
  );
  expect(within(grid).getByRole("columnheader", { name: /Template/ })).toBeTruthy();
  await within(grid).findByText("contract-review v1", {}, { timeout: 5000 });
  fireEvent.click(viewButton);
  expect(screen.queryByRole("menuitem", { name: "Rename" })).toBeNull();
  fireEvent.keyDown(screen.getByRole("menu"), { key: "Escape" });
  fireEvent.click(within(grid).getByRole("link"));
  expect(await screen.findByText(record.input_sha256)).toBeTruthy();
  expect(new URLSearchParams(router.state.location.search).get("view")).toBe("view-shared");
  expect(new URLSearchParams(router.state.location.search).get("sort")).toBe("created_at");
  expect(
    calls.every(
      (url) => !url.searchParams.has("created_by") && !url.searchParams.has("membership_id"),
    ),
  ).toBe(true);
});

it("saves a call-log layout without storing call records or drawer ids", async () => {
  serve();
  let body: Record<string, unknown> | undefined;
  let saved: Record<string, unknown> | undefined;
  server.use(
    http.get(apiUrl("/api/v1/saved-views"), () =>
      HttpResponse.json({ items: saved ? [saved] : [], next_cursor: null }),
    ),
    http.post(apiUrl("/api/v1/saved-views"), async ({ request }) => {
      body = (await request.json()) as Record<string, unknown>;
      saved = {
        ...body,
        id: "view-own",
        membership_id: signedInMe().active_membership_id,
        row_version: 1,
        created_at: "2026-10-15T10:00:00Z",
        updated_at: "2026-10-15T10:00:00Z",
      };
      return HttpResponse.json(saved, { status: 201 });
    }),
  );
  renderLog(["ai.use"], `?drawer=call&call=${id}`);
  const button = await screen.findByRole("button", { name: "View: AI calls" });
  fireEvent.click(button);
  fireEvent.click(screen.getByRole("menuitem", { name: "Save as new view" }));
  const dialog = screen.getByRole("dialog", { name: "Save as new view" });
  fireEvent.change(within(dialog).getByRole("textbox", { name: /Name/ }), {
    target: { value: "Call review" },
  });
  fireEvent.click(within(dialog).getByRole("button", { name: "Save view" }));
  await waitFor(() => expect(body?.screen_code).toBe("SF-15:ai-call-log"));
  expect(body?.is_shared).toBe(false);
  expect(JSON.stringify(body)).not.toContain(record.input_sha256);
  expect(JSON.stringify(body)).not.toContain(id);
  expect(await screen.findByRole("button", { name: "View: Call review" })).toBeTruthy();
});
