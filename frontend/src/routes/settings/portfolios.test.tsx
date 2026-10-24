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
    http.get(apiUrl("/api/v1/attachments"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
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

it.each(["RETURN_RATE", "BREAKAGE"])(
  "creates a shared %s definition with selected targets",
  async (kind) => {
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
    if (kind === "BREAKAGE") {
      fireEvent.click(screen.getByRole("combobox", { name: /Estimate kind/ }));
      fireEvent.mouseDown(screen.getByRole("option", { name: "Breakage" }));
    }
    fireEvent.change(screen.getByLabelText("Target obligation keys"), {
      target: { value: "GOODS\nSUPPORT" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Create estimate definition" }));
    await waitFor(() =>
      expect(body).toEqual({
        element_code: "RETURNS",
        estimate_kind: kind,
        method: "RATE",
        target_obligation_keys: ["GOODS", "SUPPORT"],
      }),
    );
    expect(tag).toBe('"r3"');
    await waitFor(() =>
      expect((screen.getByLabelText(/^Estimate code/) as HTMLInputElement).value).toBe(""),
    );
    expect(
      screen.getByText(/Shared return-rate versions can be submitted for independent approval/),
    ).toBeTruthy();
  },
);

it("creates and edits draft values, retains a refused edit, and discards without losing history", async () => {
  serve();
  const definition = {
    id: "e1",
    element_code: "RETURNS",
    estimate_kind: "RETURN_RATE",
    method: "RATE",
  };
  let version: Record<string, unknown> | null = null;
  const sent: { method: string; tag: string | null; body: Record<string, unknown> }[] = [];
  let stale = false;
  server.use(
    http.get(apiUrl("/api/v1/portfolios/p1/estimates"), () =>
      HttpResponse.json({ items: [definition], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/portfolios/p1/estimates/e1/versions"), () =>
      HttpResponse.json({ items: version ? [version] : [], next_cursor: null }),
    ),
    http.post(apiUrl("/api/v1/portfolios/p1/estimates/e1/versions"), async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      sent.push({ method: "POST", body, tag: request.headers.get("If-Match") });
      version = {
        ...body,
        id: "v1",
        estimate_id: "e1",
        version_no: 1,
        row_version: 1,
        status: "DRAFT",
      };
      return HttpResponse.json(version, { status: 201 });
    }),
    http.put(apiUrl("/api/v1/portfolios/p1/estimates/e1/versions/v1"), async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      sent.push({ method: "PUT", body, tag: request.headers.get("If-Match") });
      if (stale) return problemResponse("precondition-failed", 412, "The version changed");
      version = { ...version, ...body, row_version: 2 };
      return HttpResponse.json(version);
    }),
    http.post(apiUrl("/api/v1/portfolios/p1/estimates/e1/versions/v1/discard"), ({ request }) => {
      sent.push({ method: "DISCARD", body: {}, tag: request.headers.get("If-Match") });
      version = { ...version, status: "VOIDED", row_version: 3 };
      return HttpResponse.json(version);
    }),
  );
  renderApp("/settings/portfolios?row=p1", { me: editor, screenRoutes: SCREEN_ROUTES });
  fireEvent.click(await screen.findByRole("button", { name: "Versions" }));
  fireEvent.click(await screen.findByRole("button", { name: "New draft version" }));
  for (const [name, value] of [
    ["Effective date (YYYY-MM-DD)", "2026-09-01"],
    ["Currency", "USD"],
    ["Rate (0 to 1)", "0.10000001"],
    ["Rationale", "Shared experience"],
    ["Carrying cost per unit", "12.50"],
    ["Recovery cost per unit", "1.00"],
    ["Return window end (YYYY-MM-DD)", "2026-12-31"],
  ] as const) {
    fireEvent.change(screen.getByLabelText(name), { target: { value } });
  }
  fireEvent.change(screen.getByLabelText("Target obligation keys for this version"), {
    target: { value: "GOODS" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save draft version" }));
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: "Save draft version" })).toBeNull(),
  );
  expect(sent[0]?.tag).toBe('"r3"');
  expect(sent[0]?.body.rate).toBe("0.10000001");
  expect(sent[0]?.body.target_obligation_keys).toEqual(["GOODS"]);
  expect(sent[0]?.body.parameters).toEqual({
    carrying_cost_per_unit: "12.50",
    recovery_cost_per_unit: "1.00",
    window_end_date: "2026-12-31",
  });
  fireEvent.click(await screen.findByRole("button", { name: "View version" }));
  fireEvent.change(screen.getByLabelText("Rate (0 to 1)"), { target: { value: "0.15" } });
  fireEvent.click(screen.getByRole("button", { name: "Save draft version" }));
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: "Save draft version" })).toBeNull(),
  );
  expect(sent[1]?.tag).toBe('"r1"');
  stale = true;
  fireEvent.click(screen.getByRole("button", { name: "View version" }));
  fireEvent.change(screen.getByLabelText("Rate (0 to 1)"), { target: { value: "0.20" } });
  fireEvent.click(screen.getByRole("button", { name: "Save draft version" }));
  await waitFor(() => expect(sent).toHaveLength(3));
  await waitFor(() =>
    expect(
      screen.getByRole("button", { name: "Save draft version" }).getAttribute("aria-busy"),
    ).not.toBe("true"),
  );
  expect((screen.getByLabelText("Rate (0 to 1)") as HTMLInputElement).value).toBe("0.20");
  fireEvent.click(screen.getByRole("button", { name: "Close version editor" }));
  fireEvent.click(screen.getByRole("button", { name: "View version" }));
  expect((screen.getByLabelText("Rate (0 to 1)") as HTMLInputElement).value).toBe("0.15");
  fireEvent.click(screen.getByRole("button", { name: "Discard draft" }));
  await waitFor(() => expect(sent).toHaveLength(4));
  expect(sent[3]?.tag).toBe('"r2"');
  await waitFor(() => expect(screen.queryByRole("button", { name: "Discard draft" })).toBeNull());
  fireEvent.click(screen.getByRole("button", { name: "View version" }));
  expect(screen.queryByRole("button", { name: "Save draft version" })).toBeNull();
  expect((screen.getByLabelText("Rate (0 to 1)") as HTMLInputElement).value).toBe("0.15");
});

it("attaches evidence with retry-safe upload reuse and voids the uploader's attachment", async () => {
  serve();
  const version = {
    id: "v1",
    version_no: 1,
    row_version: 1,
    status: "DRAFT",
    effective_date: "2026-09-01",
    currency: "USD",
    rate: "0.1",
    parameters: {},
    scenarios: [],
    rationale: "Observed returns",
  };
  let uploads = 0;
  let attempts = 0;
  const keys: (string | null)[] = [];
  let attachment: Record<string, unknown> | null = null;
  let voidReason: unknown;
  server.use(
    http.get(apiUrl("/api/v1/portfolios/p1/estimates"), () =>
      HttpResponse.json({
        items: [
          { id: "e1", element_code: "RETURNS", estimate_kind: "RETURN_RATE", method: "RATE" },
        ],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl("/api/v1/portfolios/p1/estimates/e1/versions"), () =>
      HttpResponse.json({ items: [version], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/attachments"), () =>
      HttpResponse.json({ items: attachment ? [attachment] : [], next_cursor: null }),
    ),
    http.post(apiUrl("/api/v1/files"), () => {
      uploads += 1;
      return HttpResponse.json({ id: "f1" }, { status: 201 });
    }),
    http.post(apiUrl("/api/v1/attachments"), async ({ request }) => {
      attempts += 1;
      keys.push(request.headers.get("Idempotency-Key"));
      if (attempts === 1) return problemResponse(null, 500, "Temporary storage error");
      const body = (await request.json()) as Record<string, unknown>;
      expect(body).toMatchObject({
        subject_type: "estimate_version",
        subject_id: "v1",
        file_object_id: "f1",
      });
      attachment = {
        ...body,
        id: "a1",
        original_filename: "returns.pdf",
        created_by: editor.user.id,
        created_by_kind: "USER",
        voided_at: null,
      };
      return HttpResponse.json(attachment, { status: 201 });
    }),
    http.post(apiUrl("/api/v1/attachments/a1/void"), async ({ request }) => {
      voidReason = await request.json();
      attachment = null;
      return HttpResponse.json({ id: "a1" });
    }),
  );
  renderApp("/settings/portfolios?row=p1", { me: editor, screenRoutes: SCREEN_ROUTES });
  fireEvent.click(await screen.findByRole("button", { name: "Versions" }));
  fireEvent.click(await screen.findByRole("button", { name: "View version" }));
  fireEvent.change(await screen.findByLabelText(/^Evidence files/), {
    target: { files: [new File(["evidence"], "returns.pdf", { type: "application/pdf" })] },
  });
  fireEvent.click(screen.getByRole("button", { name: "Upload and attach evidence" }));
  await screen.findByText("Temporary storage error");
  fireEvent.click(screen.getByRole("button", { name: "Upload and attach evidence" }));
  const link = await screen.findByRole("link", { name: "returns.pdf" });
  expect(link.getAttribute("href")).toBe("/api/v1/files/f1/content");
  expect(uploads).toBe(1);
  expect(attempts).toBe(2);
  expect(keys[0]).toBeTruthy();
  expect(keys[1]).toBe(keys[0]);
  fireEvent.click(screen.getByRole("button", { name: "Void attachment" }));
  fireEvent.change(screen.getByLabelText(/^Reason for voiding/), {
    target: { value: "Replace outdated support" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Confirm void attachment" }));
  await waitFor(() => expect(screen.queryByRole("link", { name: "returns.pdf" })).toBeNull());
  expect(voidReason).toEqual({ reason: "Replace outdated support" });
});

it("authors the shared breakage total without a member rate", async () => {
  serve();
  let body: Record<string, unknown> | null = null;
  server.use(
    http.get(apiUrl("/api/v1/portfolios/p1/estimates"), () =>
      HttpResponse.json({
        items: [{ id: "e1", element_code: "BREAKAGE", estimate_kind: "BREAKAGE", method: "RATE" }],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl("/api/v1/portfolios/p1/estimates/e1/versions"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.post(apiUrl("/api/v1/portfolios/p1/estimates/e1/versions"), async ({ request }) => {
      body = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(
        { ...body, id: "v1", version_no: 1, row_version: 1, status: "DRAFT" },
        { status: 201 },
      );
    }),
  );
  renderApp("/settings/portfolios?row=p1", { me: editor, screenRoutes: SCREEN_ROUTES });
  fireEvent.click(await screen.findByRole("button", { name: "Versions" }));
  fireEvent.click(await screen.findByRole("button", { name: "New draft version" }));
  expect(screen.queryByLabelText("Rate (0 to 1)")).toBeNull();
  for (const [name, value] of [
    ["Effective date (YYYY-MM-DD)", "2026-10-23"],
    ["Currency", "USD"],
    ["Rationale", "Portfolio experience"],
    ["Portfolio total breakage quantity (allocated by SSP)", "12.000000000000000001"],
    ["Target obligation keys for this version", "POINTS"],
  ] as const)
    fireEvent.change(screen.getByLabelText(name), { target: { value } });
  fireEvent.click(screen.getByRole("button", { name: "Save draft version" }));
  await waitFor(() =>
    expect(body).toMatchObject({
      rate: null,
      expected_quantity: null,
      parameters: { portfolio_total_breakage_quantity: "12.000000000000000001" },
      target_obligation_keys: ["POINTS"],
    }),
  );
});

it("previews saved shared breakage sources and clears obsolete shares on a refused refresh", async () => {
  serve();
  let refuse = false;
  let changedSource = false;
  let changedTarget = false;
  let reads = 0;
  let retained: Record<string, unknown> | null = null;
  const requestedBooks: (string | null)[] = [];
  const version = {
    id: "v1",
    version_no: 1,
    row_version: 1,
    status: "DRAFT",
    effective_date: "2026-09-01",
    currency: "USD",
    scenarios: [],
    rationale: "Shared breakage",
    parameters: { portfolio_total_breakage_quantity: "9" },
  };
  server.use(
    http.post(
      apiUrl("/api/v1/portfolios/p1/estimates/e1/versions/v1/retain-allocation"),
      async ({ request }) => {
        expect(request.headers.get("if-match")).toBe('"r1"');
        retained = (await request.json()) as Record<string, unknown>;
        return HttpResponse.json({
          ...version,
          row_version: 2,
          portfolio_application_basis: {
            schema_version: 1,
            portfolio_id: "p1",
            members: [],
            breakage_allocations: {
              IFRS15: { schema_version: 1, sha256: "b".repeat(64), allocation: retained },
            },
          },
        });
      },
    ),
    http.get(apiUrl("/api/v1/portfolios/p1/estimates"), () =>
      HttpResponse.json({
        items: [{ id: "e1", element_code: "BREAKAGE", estimate_kind: "BREAKAGE", method: "RATE" }],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl("/api/v1/portfolios/p1/estimates/e1/versions"), () =>
      HttpResponse.json({ items: [version], next_cursor: null }),
    ),
    http.get(
      apiUrl("/api/v1/portfolios/p1/estimates/e1/versions/v1/allocation-preview"),
      ({ request }) => {
        reads++;
        const book = new URL(request.url).searchParams.get("book_code");
        requestedBooks.push(book);
        if (refuse) return problemResponse("validation-failed", 422, "Recompute every member");
        return HttpResponse.json({
          basis: "EFFECTIVE_DATE_SSP_PREVIEW",
          effective_date: "2026-10-01",
          portfolio_id: "p1",
          version_id: "v1",
          book_code: book ?? "PRIMARY",
          currency: "USD",
          total_breakage_quantity: "9",
          allocated_total: "9",
          shares: [
            {
              contract_id: "c1",
              contract_external_id: "LOYALTY-A",
              computation_id: changedSource ? "new-computation" : "original-computation",
              computation_output_sha256: "a".repeat(64),
              contract_version_id: book ? "ifrs-source" : "retained-source-1",
              obligation_id: changedTarget ? "o2" : "o1",
              obligation_key: changedTarget ? "NEW-POINTS" : "POINTS",
              ssp: "100",
              ssp_conversion: {
                original_ssp: "80",
                source_currency: "GBP",
                target_currency: "USD",
                converted_ssp: "100",
                rate: "1.25",
                effective_date: "2026-10-01",
                rate_key: "GBP-USD-SPOT",
                rate_version_key: "fx-v1",
                rate_date: "2026-09-30",
              },
              entitlement_quantity: "10",
              breakage_quantity: "3",
            },
          ],
        });
      },
    ),
  );
  renderApp("/settings/portfolios?row=p1", { me: editor, screenRoutes: SCREEN_ROUTES });
  fireEvent.click(await screen.findByRole("button", { name: "Versions" }));
  fireEvent.click(await screen.findByRole("button", { name: "View version" }));
  const button = await screen.findByRole("button", { name: "Preview SSP allocation" });
  expect(reads).toBe(0);
  fireEvent.click(button);
  await screen.findByText("retained-source-1");
  expect(screen.getByText("SSP currency conversion")).toBeTruthy();
  expect(screen.getByText(/80 GBP.*1.25.*100.*USD/)).toBeTruthy();
  expect(screen.getByText(/GBP-USD-SPOT.*fx-v1.*2026-09-30/)).toBeTruthy();
  expect(screen.getByText(/Allocated \/ shared total: 9 \/ 9/)).toBeTruthy();
  fireEvent.click(screen.getByRole("combobox", { name: "Allocation book" }));
  fireEvent.mouseDown(screen.getByRole("option", { name: "IFRS15" }));
  await waitFor(() => expect(screen.queryByText("retained-source-1")).toBeNull());
  expect(reads).toBe(1);
  fireEvent.click(button);
  await screen.findByText("ifrs-source");
  expect(requestedBooks).toEqual([null, "IFRS15"]);
  refuse = true;
  fireEvent.click(button);
  await waitFor(() => expect(reads).toBe(3));
  await waitFor(() => expect(screen.queryByText("ifrs-source")).toBeNull());
  refuse = false;
  fireEvent.click(button);
  await screen.findByText("ifrs-source");
  fireEvent.click(screen.getByRole("button", { name: "Save this allocation basis" }));
  await screen.findByText(/Saved allocation basis: IFRS15/);
  expect(retained).toMatchObject({ book_code: "IFRS15", version_id: "v1", allocated_total: "9" });
  fireEvent.click(screen.getByRole("combobox", { name: "Allocation book" }));
  fireEvent.mouseDown(screen.getByRole("option", { name: "IFRS15" }));
  fireEvent.click(screen.getByRole("button", { name: "Preview SSP allocation" }));
  await screen.findByText(
    "Saved allocation matches this preview. Saving still rechecks the sources.",
  );
  changedSource = true;
  fireEvent.click(screen.getByRole("button", { name: "Preview SSP allocation" }));
  await screen.findByText(
    "Saved allocation differs from this preview. Review the changes before saving a replacement.",
  );
  expect(screen.getByRole("table", { name: "Allocation changes" })).toBeTruthy();
  expect(screen.getByText("Changed source or quantity")).toBeTruthy();
  expect(screen.getAllByText("new-computation").length).toBeGreaterThan(0);
  changedTarget = true;
  fireEvent.click(screen.getByRole("button", { name: "Preview SSP allocation" }));
  await screen.findByText("Added target");
  expect(screen.getByText("Removed target")).toBeTruthy();
  refuse = true;
  fireEvent.click(screen.getByRole("button", { name: "Preview SSP allocation" }));
  await waitFor(() =>
    expect(screen.queryByRole("table", { name: "Allocation changes" })).toBeNull(),
  );
  expect(screen.getByText(/Saved allocation basis: IFRS15/)).toBeTruthy();
});

it.each(["RETURN_RATE", "BREAKAGE"])(
  "calculates %s impact on demand and shows period changes without posting",
  async (kind) => {
    serve();
    let reads = 0;
    const money = (amount: string) => ({ amount, currency: "USD" });
    server.use(
      http.get(apiUrl("/api/v1/portfolios/p1/estimates"), () =>
        HttpResponse.json({
          items: [{ id: "e1", element_code: "RETURNS", estimate_kind: kind, method: "RATE" }],
          next_cursor: null,
        }),
      ),
      http.get(apiUrl("/api/v1/portfolios/p1/estimates/e1/versions"), () =>
        HttpResponse.json({
          items: [
            {
              id: "v1",
              version_no: 1,
              row_version: 1,
              status: "DRAFT",
              effective_date: "2026-09-01",
              currency: "USD",
              rate: "0.08",
              parameters: {},
              scenarios: [],
              rationale: "Shared returns",
              portfolio_application_basis: {
                schema_version: 1,
                portfolio_id: "p1",
                members: [
                  {
                    contract_id: "c1",
                    contract_key: "BOUND-MEMBER",
                    obligation_ids: ["o1"],
                    obligation_keys: ["GOODS"],
                  },
                ],
              },
            },
          ],
          next_cursor: null,
        }),
      ),
      http.get(apiUrl("/api/v1/portfolios/p1/estimates/e1/versions/v1/impact-preview"), () => {
        reads++;
        if (reads > 1)
          return problemResponse("validation-failed", 422, "Recompute affected groups");
        return HttpResponse.json({
          basis: kind === "BREAKAGE" ? "SHARED_BREAKAGE_DRY_RUN" : "SHARED_RETURN_DRY_RUN",
          portfolio_id: "p1",
          version_id: "v1",
          groups: [
            {
              combination_group_id: "g1",
              book_code: "ASC606",
              currency: "USD",
              catch_up_amount: "400.00",
              source_contract_version_id: "baseline-version",
              source_computation_id: "calc1",
              input_sha256: "a".repeat(64),
              members: [
                {
                  contract_id: "c1",
                  contract_external_id: "RETURNS-A",
                  balances_before: [{ balance: "revenue", amount: money("9600.00") }],
                  balances_after: [{ balance: "revenue", amount: money("9200.00") }],
                  revenue_by_period: [
                    {
                      period_key: "FY2026-P01",
                      before: money("9600.00"),
                      after: money("9200.00"),
                      change: money("-400.00"),
                    },
                  ],
                },
              ],
            },
          ],
        });
      }),
    );
    renderApp("/settings/portfolios?row=p1", { me: editor, screenRoutes: SCREEN_ROUTES });
    fireEvent.click(await screen.findByRole("button", { name: "Versions" }));
    fireEvent.click(await screen.findByRole("button", { name: "View version" }));
    const button = await screen.findByRole("button", { name: "Calculate shared impact" });
    expect(reads).toBe(0);
    expect(screen.getByText("BOUND-MEMBER: GOODS")).toBeTruthy();
    fireEvent.click(button);
    await screen.findByText("-400.00");
    expect(screen.getByText("baseline-version", { exact: false })).toBeTruthy();
    fireEvent.click(button);
    await waitFor(() => expect(reads).toBe(2));
    await waitFor(() => expect(screen.queryByText("-400.00")).toBeNull());
  },
);

it("submits saved shared returns with an ETag and opens the resulting approval", async () => {
  serve();
  let version = {
    id: "v1",
    version_no: 1,
    row_version: 4,
    status: "DRAFT",
    effective_date: "2026-09-01",
    currency: "USD",
    rate: "0.1",
    parameters: {},
    scenarios: [],
    rationale: "Observed returns",
    approval_request_id: null as string | null,
    portfolio_application_basis: {
      schema_version: 1,
      target_obligation_keys: ["NEW-GOODS"],
      retired_targets: [
        {
          contract_id: "c1",
          contract_key: "CONTRACT-1",
          obligation_ids: ["old"],
          obligation_keys: ["OLD-GOODS"],
        },
      ],
      portfolio_id: "p1",
      members: [],
      cost_conversions: [
        {
          source_currency: "GBP",
          target_currency: "USD",
          rate: "1.25",
          rate_date: "2026-10-01",
          rate_key: "COST-SPOT@v1/GBP/USD/2026-10-01",
          rate_version_key: "COST-SPOT@v1",
          original_costs: { carrying_cost_per_unit: "12.50", recovery_cost_per_unit: "0.01" },
          converted_costs: { carrying_cost_per_unit: "15.625", recovery_cost_per_unit: "0.0125" },
        },
      ],
      retired_members: [
        {
          contract_id: "c1",
          contract_key: "CONTRACT-1",
          obligation_ids: ["o1"],
          obligation_keys: ["GOODS"],
        },
      ],
    },
  };
  let tag: string | null = null;
  server.use(
    http.get(apiUrl("/api/v1/portfolios/p1/estimates"), () =>
      HttpResponse.json({
        items: [
          { id: "e1", element_code: "RETURNS", estimate_kind: "RETURN_RATE", method: "RATE" },
        ],
        next_cursor: null,
      }),
    ),
    http.get(apiUrl("/api/v1/portfolios/p1/estimates/e1/versions"), () =>
      HttpResponse.json({ items: [version], next_cursor: null }),
    ),
    http.post(apiUrl("/api/v1/portfolios/p1/estimates/e1/versions/v1/submit"), ({ request }) => {
      tag = request.headers.get("If-Match");
      version = { ...version, status: "SUBMITTED", row_version: 5, approval_request_id: "a1" };
      return HttpResponse.json(version);
    }),
  );
  renderApp("/settings/portfolios?row=p1", { me: editor, screenRoutes: SCREEN_ROUTES });
  fireEvent.click(await screen.findByRole("button", { name: "Versions" }));
  fireEvent.click(await screen.findByRole("button", { name: "View version" }));
  expect(
    screen.getByRole("heading", { name: "Members leaving this shared estimate" }),
  ).toBeTruthy();
  expect(screen.getByText("CONTRACT-1: GOODS")).toBeTruthy();
  expect(
    screen.getByRole("heading", { name: "Obligations leaving this shared estimate" }),
  ).toBeTruthy();
  expect(screen.getByText("CONTRACT-1: OLD-GOODS")).toBeTruthy();
  expect(
    (screen.getByLabelText("Target obligation keys for this version") as HTMLTextAreaElement).value,
  ).toBe("NEW-GOODS");
  expect(
    screen.getByRole("heading", { name: "Saved unit-cost currency conversions" }),
  ).toBeTruthy();
  expect(screen.getByText("Carrying cost per unit: 12.50 GBP → 15.625 USD")).toBeTruthy();
  expect(screen.getByText(/COST-SPOT@v1 · COST-SPOT@v1\/GBP\/USD/)).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Rate (0 to 1)"), { target: { value: "0.2" } });
  expect(
    screen.getByRole("button", { name: "Submit for approval" }).getAttribute("aria-disabled"),
  ).toBe("true");
  fireEvent.change(screen.getByLabelText("Rate (0 to 1)"), { target: { value: "0.1" } });
  fireEvent.click(screen.getByRole("button", { name: "Submit for approval" }));
  await waitFor(() => expect(tag).toBe('"r4"'));
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: "Submit for approval" })).toBeNull(),
  );
  fireEvent.click(screen.getByRole("button", { name: "View version" }));
  expect(
    (await screen.findByRole("link", { name: "View approval request" })).getAttribute("href"),
  ).toBe("/approvals/requests/a1");
  expect(
    screen.getByRole("button", { name: "Withdraw submission" }).getAttribute("aria-disabled"),
  ).toBeNull();
});
