// @vitest-environment jsdom
// SF-24:results (BUILD_SPEC CTR-28; SCREENS §1.4, §0.4 RT-95; 04 API-R-55): `/search?q=<query>` reads
// `GET /search?q=<query>&limit=25` once and renders `h1` "Search results for "<query>"" over one table
// a scope that found something, captioned by the scope, with the columns of §1.4 and the routes built
// from scope and id; "Show more <scope>" reads the next page by the scope's cursor; the chip "Scope"
// (`f.scope=is:<scope>`) sends `scope`; a text the route would refuse is not sent; without
// `contract.read` the page is the access-limited screen and nothing is read.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import { searchResultsRoute } from "../../lib/api/queries/search";
import { installMemoryStorage, renderApp, signedInMe } from "../../test/app";
import { installMswServer } from "../../test/msw";
import {
  gate,
  K01_ID,
  K02_ID,
  manyContracts,
  OBLIGATION_ID,
  OTHER_OBLIGATION_ID,
  PELLWORTH_ID,
  RUN_ID,
  serveSearch,
  SF_ORD,
} from "../../test/search";

installMswServer();
installMemoryStorage();

afterEach(() => {
  cleanup();
});

const READER = signedInMe({ permissions: ["contract.read"] });

function open(search: string, me = READER) {
  return renderApp(`/search${search}`, { me, screenRoutes: SCREEN_ROUTES });
}

function headers(table: HTMLElement): (string | null)[] {
  return within(table)
    .getAllByRole("columnheader")
    .map((header) => header.textContent);
}

/** The rows of a table as their cell texts. */
function rows(table: HTMLElement): (string | null)[][] {
  return within(table)
    .getAllByRole("row")
    .slice(1)
    .map((row) => Array.from(row.querySelectorAll("th, td"), (cell) => cell.textContent));
}

function linkOf(table: HTMLElement, name: string): string | null {
  return within(table).getByRole("link", { name }).getAttribute("href");
}

const NO_MATCHES = (query: string) =>
  `No matches for "${query}". Search by contract number, customer, invoice number or order number.`;

describe("SF-24:results", () => {
  it("renders a table a scope with the columns of SCREENS §1.4 and the routes built from scope and id", async () => {
    const world = serveSearch();
    open("?q=SF-ORD");

    expect(
      await screen.findByRole("heading", { level: 1, name: 'Search results for "SF-ORD"' }),
    ).toBeTruthy();
    const contracts = await screen.findByRole("table", { name: "Contracts" });
    // One read for the page: every scope, 25 rows a scope.
    expect(world.searches).toEqual([{ q: "SF-ORD", limit: "25" }]);
    expect(
      screen.getAllByRole("table").map((table) => table.querySelector("caption")?.textContent),
    ).toEqual(["Contracts", "Customers", "Invoices", "Obligations"]);

    expect(headers(contracts)).toEqual(["Contract", "Customer", "Status"]);
    expect(rows(contracts)).toEqual([
      ["SF-ORD-10001", "Pellworth Logistics Inc. (Demo)", "Active"],
      ["SF-ORD-10002", "Marrowby Health Partners LLC (Demo)", "Pending approval"],
    ]);
    expect(linkOf(contracts, "SF-ORD-10001")).toBe(`/contracts/${K01_ID}/obligations`);
    expect(linkOf(contracts, "SF-ORD-10002")).toBe(`/contracts/${K02_ID}/obligations`);

    const customers = screen.getByRole("table", { name: "Customers" });
    expect(headers(customers)).toEqual(["Code", "Customer"]);
    expect(rows(customers)).toEqual([["SF-ORD-HOLDINGS", "Pellworth Logistics Inc. (Demo)"]]);
    expect(linkOf(customers, "SF-ORD-HOLDINGS")).toBe(`/settings/customers/${PELLWORTH_ID}`);

    // An invoice opens the Billing tab of the contract its `href` names.
    const invoices = screen.getByRole("table", { name: "Invoices" });
    expect(headers(invoices)).toEqual(["Invoice", "Contract"]);
    expect(rows(invoices)).toEqual([["INV-2026-0042", "SF-ORD-10001"]]);
    expect(linkOf(invoices, "INV-2026-0042")).toBe(`/contracts/${K01_ID}/billing`);

    // An obligation's route needs its contract: `GET /obligations/{id}` for each row shown. A
    // literal that shows no chip (E-22 PARTIALLY_SATISFIED) leaves the cell empty.
    const obligations = screen.getByRole("table", { name: "Obligations" });
    expect(headers(obligations)).toEqual(["Obligation", "Product", "Status"]);
    expect(rows(obligations)).toEqual([
      ["SF-ORD-10001 · O1", "Platform subscription", "Satisfied"],
      ["SF-ORD-10002 · O1", "Platform seat, per seat", ""],
    ]);
    await waitFor(() => {
      expect(linkOf(obligations, "SF-ORD-10001 · O1")).toBe(
        `/contracts/${K01_ID}/obligations/${OBLIGATION_ID}`,
      );
    });
    expect(linkOf(obligations, "SF-ORD-10002 · O1")).toBe(
      `/contracts/${K02_ID}/obligations/${OTHER_OBLIGATION_ID}`,
    );
    expect([...world.obligationReads].sort()).toEqual([OBLIGATION_ID, OTHER_OBLIGATION_ID]);

    // Nothing more to read in any scope, and no table for a scope that found nothing.
    expect(screen.queryByRole("button", { name: /^Show more/ })).toBeNull();
    expect(screen.queryByRole("table", { name: "Journals" })).toBeNull();
    cleanup();

    // A journal run is found by its period: the run number, the period and entity, its state.
    open("?q=FY2026-P09");
    const journals = await screen.findByRole("table", { name: "Journals" });
    expect(screen.getAllByRole("table")).toEqual([journals]);
    expect(headers(journals)).toEqual(["Run", "Period and entity", "State"]);
    expect(rows(journals)).toEqual([["JR-000118", "FY2026-P09 · AVM-US", "Calculated"]]);
    expect(linkOf(journals, "JR-000118")).toBe(`/journals/runs/${RUN_ID}`);
  });

  it("Show more contracts reads the next page by the scope's cursor and adds its rows", async () => {
    const world = serveSearch({ ...SF_ORD, contracts: manyContracts(60) });
    open("?q=BG-AVM");

    const contracts = await screen.findByRole("table", { name: "Contracts" });
    expect(rows(contracts)).toHaveLength(25);
    expect(rows(contracts).at(-1)?.[0]).toBe("BG-AVM-0025");
    // The other scopes found nothing for "BG-AVM": no table for them.
    expect(screen.getAllByRole("table")).toHaveLength(1);

    const [held, release] = gate();
    world.hold = held;
    const more = screen.getByRole("button", { name: "Show more contracts" });
    fireEvent.click(more);
    await waitFor(() => {
      expect(world.searches.at(-1)).toEqual({
        q: "BG-AVM",
        scope: "contracts",
        limit: "25",
        cursor: "contracts:25",
      });
    });
    expect(more.getAttribute("aria-busy")).toBe("true");
    release();
    world.hold = null;
    await waitFor(() => {
      expect(rows(contracts)).toHaveLength(50);
    });
    expect(rows(contracts).at(-1)?.[0]).toBe("BG-AVM-0050");

    // The third page is the last: its cursor is null and the button leaves.
    fireEvent.click(screen.getByRole("button", { name: "Show more contracts" }));
    await waitFor(() => {
      expect(rows(contracts)).toHaveLength(60);
    });
    expect(world.searches.at(-1)).toEqual({
      q: "BG-AVM",
      scope: "contracts",
      limit: "25",
      cursor: "contracts:50",
    });
    expect(screen.queryByRole("button", { name: "Show more contracts" })).toBeNull();
    expect(world.searches).toHaveLength(3);
  });

  it("a next page that cannot be read says so under its table, and Retry reads it again", async () => {
    const world = serveSearch({ contracts: manyContracts(30) });
    open("?q=BG-AVM");
    const contracts = await screen.findByRole("table", { name: "Contracts" });

    world.failWith = 500;
    fireEvent.click(screen.getByRole("button", { name: "Show more contracts" }));
    const section = screen.getByTestId("SF-24-results-contracts");
    expect(await within(section).findByText("Could not load more results")).toBeTruthy();
    // The rows read before stay.
    expect(rows(contracts)).toHaveLength(25);

    world.failWith = null;
    fireEvent.click(within(section).getByRole("button", { name: "Retry" }));
    await waitFor(() => {
      expect(rows(contracts)).toHaveLength(30);
    });
    expect(within(section).queryByText("Could not load more results")).toBeNull();
  });

  it("the chip Scope sends scope and shows that table alone, and the quick search writes q", async () => {
    const world = serveSearch();
    // The link "Show all results" of the palette writes under its chip "Obligations".
    expect(searchResultsRoute("SF-ORD", "obligations")).toBe(
      "/search?q=SF-ORD&f.scope=is:obligations",
    );
    const { router } = renderApp(searchResultsRoute("SF-ORD", "obligations"), {
      me: READER,
      screenRoutes: SCREEN_ROUTES,
    });

    const obligations = await screen.findByRole("table", { name: "Obligations" });
    expect(world.searches).toEqual([{ q: "SF-ORD", scope: "obligations", limit: "25" }]);
    expect(screen.getAllByRole("table")).toEqual([obligations]);
    const filters = screen.getByTestId("SF-24-filters");
    expect(within(filters).getByRole("button", { name: "Remove filter: Scope" })).toBeTruthy();
    expect(within(filters).getByText("Scope is Obligations")).toBeTruthy();
    expect(
      screen.queryByText("Some filters in the link were not recognised and were removed."),
    ).toBeNull();

    // Removing the chip searches every scope again.
    fireEvent.click(within(filters).getByRole("button", { name: "Remove filter: Scope" }));
    await screen.findByRole("table", { name: "Contracts" });
    expect(world.searches.at(-1)).toEqual({ q: "SF-ORD", limit: "25" });
    expect(router.state.location.search).toBe("?q=SF-ORD");

    // The quick search holds the text of the URL and writes it back, 250 ms after the last key.
    const quick = within(filters).getByRole("searchbox", { name: "Search records" });
    expect((quick as HTMLInputElement).value).toBe("SF-ORD");
    fireEvent.change(quick, { target: { value: "marrow" } });
    await waitFor(() => {
      expect(router.state.location.search).toBe("?q=marrow");
    });
    expect(
      await screen.findByRole("heading", { level: 1, name: 'Search results for "marrow"' }),
    ).toBeTruthy();
    await waitFor(() => {
      expect(world.searches.at(-1)).toEqual({ q: "marrow", limit: "25" });
    });
    // The table is asked for anew: the one of the text before leaves while the next answer loads.
    await waitFor(() => {
      expect(rows(screen.getByRole("table", { name: "Contracts" }))).toEqual([
        ["SF-ORD-10002", "Marrowby Health Partners LLC (Demo)", "Pending approval"],
      ]);
    });
    expect(screen.getAllByRole("table")).toHaveLength(1);
  });

  it("a text the route would refuse is not sent; no match and a failed read say so", async () => {
    const world = serveSearch();
    // No text, one character, no letter or digit: 04 API-R-55 answers each with 422.
    for (const search of ["", "?q=S", "?q=--", "?q=%20%20a%20"]) {
      open(search);
      expect(await screen.findByText("Type at least 2 characters to search.")).toBeTruthy();
      expect(screen.queryByRole("table")).toBeNull();
      cleanup();
    }
    open("");
    expect(await screen.findByRole("heading", { level: 1, name: "Search results" })).toBeTruthy();
    cleanup();
    expect(world.searches).toEqual([]);

    open("?q=zz-nothing");
    expect(await screen.findByText(NO_MATCHES("zz-nothing"))).toBeTruthy();
    expect(screen.queryByRole("table")).toBeNull();
    cleanup();

    world.failWith = 500;
    open("?q=SF-ORD");
    expect(await screen.findByText("Could not load the search results")).toBeTruthy();
    world.failWith = null;
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(await screen.findByRole("table", { name: "Contracts" })).toBeTruthy();
    expect(screen.queryByText("Could not load the search results")).toBeNull();
  });

  it("without contract.read the page is the access-limited screen and reads nothing", async () => {
    const world = serveSearch();
    open("?q=SF-ORD", signedInMe({ permissions: ["report.run"] }));
    expect(
      await screen.findByRole("heading", { level: 2, name: "You do not have access to search" }),
    ).toBeTruthy();
    expect(
      screen.getByText("Ask a workspace administrator for a role that includes viewing contracts."),
    ).toBeTruthy();
    expect(screen.queryByTestId("SF-24-filters")).toBeNull();
    expect(screen.queryByRole("table")).toBeNull();
    expect(world.searches).toEqual([]);
  });
});
