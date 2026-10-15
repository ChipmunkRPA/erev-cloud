// @vitest-environment jsdom
import { cleanup, screen, fireEvent, within } from "@testing-library/react";
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
