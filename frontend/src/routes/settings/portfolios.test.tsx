// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import { installMemoryStorage, renderApp, signedInMe } from "../../test/app";
import { installGridViewport } from "../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";

installMswServer();
installMemoryStorage();
installGridViewport();
afterEach(cleanup);
const editor = signedInMe({ permissions: ["contract.read", "estimate.create"] });
const portfolio = {
  id: "p1",
  code: "RETURNS",
  name: "Similar returns",
  row_version: 3,
  product_group: null,
  description: null,
  created_at: "2026-10-23T10:00:00Z",
  updated_at: "2026-10-23T10:00:00Z",
};
const member = {
  id: "m1",
  portfolio_id: "p1",
  contract_id: "c1",
  contract_external_id: "CONTRACT-1",
  contracting_entity_id: "e1",
  valid_from_known_at: "2026-10-23T10:00:00Z",
  valid_to_known_at: null,
  portfolio_row_version: 3,
};
function serve() {
  server.use(
    http.get(apiUrl("/api/v1/portfolios/p1/estimates"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/portfolios"), () =>
      HttpResponse.json({ items: [portfolio], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/portfolios/p1"), () => HttpResponse.json(portfolio)),
    http.get(apiUrl("/api/v1/portfolios/p1/members"), () =>
      HttpResponse.json({ items: [member], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/contracts"), () =>
      HttpResponse.json({
        items: [
          { id: "c2", external_id: "CONTRACT-2", contracting_entity: { id: "e1", code: "US" } },
        ],
        next_cursor: null,
      }),
    ),
  );
}
it("creates a portfolio and opens its membership page", async () => {
  serve();
  let body: unknown;
  server.use(
    http.post(apiUrl("/api/v1/portfolios"), async ({ request }) => {
      body = await request.json();
      return HttpResponse.json(portfolio, { status: 201 });
    }),
  );
  renderApp("/settings/portfolios?row=new", { me: editor, screenRoutes: SCREEN_ROUTES });
  fireEvent.change(await screen.findByLabelText(/^Code/), { target: { value: "RETURNS" } });
  fireEvent.change(screen.getByLabelText(/^Name/), { target: { value: "Similar returns" } });
  fireEvent.click(screen.getByRole("button", { name: "Save portfolio" }));
  await screen.findByRole("button", { name: "Add member" });
  expect(body).toEqual({
    code: "RETURNS",
    name: "Similar returns",
    product_group: null,
    description: null,
  });
});
it("joins and removes with the parent ETag, rationale and retained history", async () => {
  serve();
  const requests: { path: string; body: unknown; tag: string | null }[] = [];
  let history = false;
  server.use(
    http.post(apiUrl("/api/v1/portfolios/p1/members"), async ({ request }) => {
      requests.push({
        path: "join",
        body: await request.json(),
        tag: request.headers.get("If-Match"),
      });
      return HttpResponse.json({ ...member, contract_id: "c2" }, { status: 201 });
    }),
    http.post(apiUrl("/api/v1/portfolios/p1/members/c1/remove"), async ({ request }) => {
      requests.push({
        path: "remove",
        body: await request.json(),
        tag: request.headers.get("If-Match"),
      });
      return HttpResponse.json({ ...member, valid_to_known_at: "2026-10-24T10:00:00Z" });
    }),
    http.get(apiUrl("/api/v1/portfolios/p1/members"), ({ request }) => {
      history = new URL(request.url).searchParams.get("include_history") === "true";
      return HttpResponse.json({ items: [member], next_cursor: null });
    }),
  );
  renderApp("/settings/portfolios?row=p1", { me: editor, screenRoutes: SCREEN_ROUTES });
  fireEvent.click(await screen.findByRole("button", { name: "Add member" }));
  fireEvent.click(await screen.findByRole("radio", { name: "CONTRACT-2" }));
  fireEvent.change(screen.getByLabelText(/^Reason for membership change/), {
    target: { value: "Similar terms" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Confirm membership change" }));
  await waitFor(() => expect(requests).toHaveLength(1));
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: "Confirm membership change" })).toBeNull(),
  );
  fireEvent.click(await screen.findByRole("button", { name: "Remove member" }));
  fireEvent.change(screen.getByLabelText(/^Reason for membership change/), {
    target: { value: "Terms changed" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Confirm membership change" }));
  await waitFor(() => expect(requests).toHaveLength(2));
  expect(requests).toEqual([
    { path: "join", body: { contract_id: "c2", rationale: "Similar terms" }, tag: '"r3"' },
    { path: "remove", body: { rationale: "Terms changed" }, tag: '"r3"' },
  ]);
  fireEvent.click(screen.getByLabelText("Include membership history"));
  await waitFor(() => expect(history).toBe(true));
});
it("retains edits after a stale version refusal and explicitly reloads latest values", async () => {
  serve();
  server.use(
    http.put(apiUrl("/api/v1/portfolios/p1"), () => {
      server.use(
        http.get(apiUrl("/api/v1/portfolios/p1"), () =>
          HttpResponse.json({ ...portfolio, name: "Other editor", row_version: 4 }),
        ),
      );
      return problemResponse("precondition-failed", 412, "The portfolio changed");
    }),
  );
  renderApp("/settings/portfolios?row=p1", { me: editor, screenRoutes: SCREEN_ROUTES });
  fireEvent.change(await screen.findByLabelText(/^Name/), { target: { value: "My edits" } });
  fireEvent.click(screen.getByRole("button", { name: "Save portfolio" }));
  const reload = await screen.findByRole("button", {
    name: "Reload latest portfolio (discard edits)",
  });
  expect((screen.getByLabelText(/^Name/) as HTMLInputElement).value).toBe("My edits");
  fireEvent.click(reload);
  await waitFor(() =>
    expect((screen.getByLabelText(/^Name/) as HTMLInputElement).value).toBe("Other editor"),
  );
});
it("shows portfolio and member history to a reader without editing controls", async () => {
  serve();
  renderApp("/settings/portfolios?row=p1", {
    me: signedInMe({ permissions: ["contract.read"] }),
    screenRoutes: SCREEN_ROUTES,
  });
  await screen.findByLabelText("Include membership history");
  expect(screen.queryByRole("button", { name: "Add member" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Save portfolio" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Remove member" })).toBeNull();
});

it("creates a shared definition with the portfolio version and leaves application unavailable", async () => {
  serve();
  let body: unknown;
  let tag: string | null = null;
  server.use(
    http.post(apiUrl("/api/v1/portfolios/p1/estimates"), async ({ request }) => {
      body = await request.json();
      tag = request.headers.get("If-Match");
      return HttpResponse.json({ id: "e1" }, { status: 201 });
    }),
  );
  renderApp("/settings/portfolios?row=p1", { me: editor, screenRoutes: SCREEN_ROUTES });
  fireEvent.change(await screen.findByLabelText(/^Estimate code/), {
    target: { value: "RETURNS" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Create estimate definition" }));
  await waitFor(() =>
    expect(body).toEqual({ element_code: "RETURNS", estimate_kind: "RETURN_RATE", method: "RATE" }),
  );
  expect(tag).toBe('"r3"');
  await waitFor(() =>
    expect((screen.getByLabelText(/^Estimate code/) as HTMLInputElement).value).toBe(""),
  );
  expect(
    screen.getByText(/Version values, approval and calculation application are not yet available/),
  ).toBeTruthy();
});
