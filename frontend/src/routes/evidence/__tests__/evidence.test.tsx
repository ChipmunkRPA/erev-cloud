// @vitest-environment jsdom
import { cleanup, fireEvent, screen, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeAll, beforeEach, expect, it } from "vitest";
import { SCREEN_ROUTES } from "../../../app/router";
import { installMemoryStorage, preloadScreens, renderApp, signedInMe } from "../../../test/app";
import { installGridViewport } from "../../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";
import { AUDITOR_REQUESTS, requestDestination } from "../requests";

installMswServer();
installMemoryStorage();
installGridViewport();
beforeAll(async () => {
  await preloadScreens(SCREEN_ROUTES, ["SF-09"]);
});
afterEach(() => cleanup());
const permissions = [
  "report.run",
  "audit.read",
  "contract.read",
  "report.export",
  "evidence.export",
];
const me = signedInMe({ permissions });
const reports = [...new Set(AUDITOR_REQUESTS.flatMap((row) => row.reports ?? []))].map((code) => ({
  code,
  name: `Report ${code}`,
  description: code,
  kind: "STANDARD",
  version: 1,
  output_formats: ["JSON"],
  parameters_schema: {},
  tie_outs: [],
}));
beforeEach(() => {
  server.use(
    http.get(apiUrl("/api/v1/evidence-packs"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/report-definitions"), () => HttpResponse.json({ items: reports })),
  );
});
function open(member = me) {
  return renderApp(
    "/reports/evidence?entity=AVM-US&book=ASC606&period=FY2026-P09&f.status=is:SUCCEEDED",
    { me: member, screenRoutes: SCREEN_ROUTES },
  );
}
async function ready() {
  await screen.findByText("Report je_population");
}
it("auditor requests table has the 20 specified requests and working report destinations", async () => {
  open();
  await ready();
  const table = screen.getByRole("table", { name: "Auditor requests (20)" });
  expect(within(table).getAllByRole("row")).toHaveLength(21);
  for (let i = 1; i <= 20; i++)
    expect(screen.getByTestId(`SF-09-row-a-${String(i).padStart(2, "0")}`)).not.toBeNull();
  const row = screen.getByTestId("SF-09-row-a-01");
  expect(within(row).getByText(/Complete revenue JE population/)).not.toBeNull();
  expect(within(row).getByRole("link", { name: "Run report" }).getAttribute("href")).toBe(
    "/reports/je_population?entity=AVM-US&book=ASC606&period=FY2026-P09",
  );
  expect(within(screen.getByTestId("SF-09-row-a-17")).queryAllByRole("link")).toHaveLength(0);
  expect(
    screen.getByText("Service organization reports are not part of eRev Cloud 1.0."),
  ).not.toBeNull();
});
it.each([
  ["15", "Generate access pack"],
  ["16", "Generate change pack"],
])("A-%s shows the unavailable pack action honestly", async (id, label) => {
  open();
  await ready();
  fireEvent.click(
    within(screen.getByTestId(`SF-09-row-a-${id}`)).getByRole("button", { name: "Run report" }),
  );
  expect(screen.getByRole("menuitem", { name: label }).getAttribute("aria-disabled")).toBe("true");
});
it("reconciliations and own audit events preserve the selected close context", async () => {
  open();
  await ready();
  const reconciliation = within(screen.getByTestId("SF-09-row-a-13"))
    .getByRole("link")
    .getAttribute("href");
  expect(reconciliation).toBe(
    "/close/AVM-US/ASC606/FY2026-P09/reconciliations?entity=AVM-US&book=ASC606&period=FY2026-P09",
  );
  const audit = within(screen.getByTestId("SF-09-row-a-20")).getByRole("link").getAttribute("href");
  const query = new URL(audit ?? "", "https://example.test").searchParams;
  expect(query.get("f.actor")).toBe(`is:${me.user.id}`);
  expect(query.get("period")).toBe("FY2026-P09");
  expect(query.has("f.status")).toBe(false);
});
it("does not offer generation without evidence.export", async () => {
  open(signedInMe({ permissions: permissions.filter((p) => p !== "evidence.export") }));
  await ready();
  expect(within(screen.getByTestId("SF-09-row-a-04")).queryAllByRole("button")).toHaveLength(0);
  fireEvent.click(
    within(screen.getByTestId("SF-09-row-a-15")).getByRole("button", { name: "Run report" }),
  );
  expect(screen.queryByRole("menuitem", { name: "Generate access pack" })).toBeNull();
});
it("does not invent report actions after the definition read fails", async () => {
  server.use(
    http.get(apiUrl("/api/v1/report-definitions"), () =>
      problemResponse("forbidden", 403, "Forbidden"),
    ),
  );
  open();
  await screen.findByText("Could not load available reports");
  expect(within(screen.getByTestId("SF-09-row-a-01")).queryAllByRole("link")).toHaveLength(0);
});
it("requires complete context for reconciliations and escapes identifiers", () => {
  expect(requestDestination("reconciliation", "?entity=AVM-US", me.user.id)).toBeNull();
  expect(
    requestDestination("reconciliation", "?entity=A%2FB&book=ASC606&period=FY2026-P09", me.user.id),
  ).toBe(
    "/close/A%2FB/ASC606/FY2026-P09/reconciliations?entity=A%2FB&book=ASC606&period=FY2026-P09",
  );
});
