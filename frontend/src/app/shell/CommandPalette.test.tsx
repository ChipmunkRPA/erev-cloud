// @vitest-environment jsdom
// DS-CMP-04 (DESIGN_SYSTEM §7.1; SCREENS §1.4): `Mod K` toggles the "Command palette" dialog with an APG
// combobox; typing `appr` lists "Go to Approvals" when /approvals is built and nothing for an unbuilt
// route; "Theme: Dark" sets data-theme, stores erev.theme and sends PATCH /me/preferences; Esc clears the
// query, a second Esc closes, and focus returns to the prior element. Record search (BUILD_SPEC CTR-28;
// 04 API-R-55): from two characters, 120 ms after the last key, `GET /search` lists the found records a
// scope ahead of the pages and commands; a record opens the route built from its scope and id; a scope
// chip sends `scope`; "Show all results" opens SF-24:results; the rows of the answer before stay while
// the next is on its way; Enter waits for an answer that is on its way and for the read of an
// obligation's contract; and an answer that comes after the palette has closed, or after its page has
// left, opens nothing.
import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { announce } from "../../lib/a11y/announce";
import { obligationContractKey, RECORD_ROUTE_PATTERNS } from "../../lib/api/queries/search";
import { installMemoryStorage, renderWithApp, signedInMe } from "../../test/app";
import { apiUrl, installMswServer, server } from "../../test/msw";
import {
  gate,
  K01_ID,
  K02_ID,
  OBLIGATION_ID,
  PELLWORTH_ID,
  RUN_ID,
  type SearchWorld,
  serveSearch,
} from "../../test/search";
import { CommandPalette, SEARCH_DEBOUNCE_MS } from "./CommandPalette";

vi.mock("../../lib/a11y/announce", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/a11y/announce")>();
  return { ...actual, announce: vi.fn() };
});

installMswServer();
installMemoryStorage();

let world: SearchWorld;
beforeEach(() => {
  world = serveSearch();
});

afterEach(() => {
  cleanup();
  vi.mocked(announce).mockClear();
  vi.restoreAllMocks();
});

// The routes of the rail's two built destinations, of SF-24:results and of the five record scopes.
const BUILT: ReadonlySet<string> = new Set([
  "/approvals",
  "/settings",
  "/search",
  ...Object.values(RECORD_ROUTE_PATTERNS),
]);

function renderPalette(options: Parameters<typeof renderWithApp>[1] = {}) {
  return renderWithApp(
    <>
      <input aria-label="Quick filter" />
      <CommandPalette built={BUILT} />
    </>,
    options,
  );
}

function modK(target: Element): void {
  fireEvent.keyDown(target, { key: "k", metaKey: true });
}

function optionNames(): string[] {
  return screen.getAllByRole("option").map((option) => option.textContent ?? "");
}

/** The options by what a screen reader reads: the label of a record, else the text. */
function optionLabels(): string[] {
  return screen
    .queryAllByRole("option")
    .map((option) => option.getAttribute("aria-label") ?? option.textContent ?? "");
}

function groupNames(): string[] {
  return within(screen.getByRole("listbox"))
    .getAllByRole("group")
    .map(
      (group) =>
        document.getElementById(group.getAttribute("aria-labelledby") ?? "")?.textContent ?? "",
    );
}

function activeLabel(): string | null {
  const id = screen.getByRole("combobox").getAttribute("aria-activedescendant");
  const option = id === null ? null : document.getElementById(id);
  return option === null ? null : (option.getAttribute("aria-label") ?? option.textContent);
}

/** Opens the palette and types `text`; the search is sent 120 ms later. */
function openAndType(text: string): HTMLElement {
  modK(document.body);
  const combobox = screen.getByRole("combobox");
  fireEvent.change(combobox, { target: { value: text } });
  return combobox;
}

const K01 = "SF-ORD-10001, Pellworth Logistics Inc. (Demo), Active";
const K02 = "SF-ORD-10002, Marrowby Health Partners LLC (Demo), Pending approval";
const CUSTOMER = "SF-ORD-HOLDINGS, Pellworth Logistics Inc. (Demo)";
const INVOICE = "INV-2026-0042, SF-ORD-10001";
const OBLIGATION = "SF-ORD-10001 · O1, Platform subscription, Satisfied";
const OTHER_OBLIGATION = "SF-ORD-10002 · O1, Platform seat, per seat";
const RUN = "JR-000118, FY2026-P09 · AVM-US, Calculated";
const NO_MATCHES = (query: string) =>
  `No matches for "${query}". Search by contract number, customer, invoice number or order number.`;

describe("DS-CMP-04", () => {
  it("Mod K toggles a dialog named Command palette with an APG combobox", () => {
    renderPalette();
    modK(document.body);
    const dialog = screen.getByRole("dialog", { name: "Command palette" });
    expect(dialog.getAttribute("aria-modal")).toBe("true");
    const combobox = within(dialog).getByRole("combobox");
    expect(document.activeElement).toBe(combobox);
    const listbox = within(dialog).getByRole("listbox");
    expect(combobox.getAttribute("aria-expanded")).toBe("true");
    expect(combobox.getAttribute("aria-controls")).toBe(listbox.id);
    expect(combobox.getAttribute("aria-activedescendant")).toBe(
      within(listbox).getAllByRole("option")[0]?.id,
    );
    expect(
      within(listbox)
        .getAllByRole("group")
        .map((group) => group.getAttribute("aria-labelledby")),
    ).toHaveLength(2);

    modK(combobox);
    expect(screen.queryByRole("dialog", { name: "Command palette" })).toBeNull();
  });

  it("typing appr lists Go to Approvals when /approvals is built and no command for an unbuilt route", async () => {
    renderPalette();
    modK(document.body);
    const combobox = screen.getByRole("combobox");
    fireEvent.change(combobox, { target: { value: "appr" } });
    expect(optionNames()).toEqual(["Go to Approvals"]);
    expect(announce).toHaveBeenLastCalledWith("1 result", "polite");

    fireEvent.change(combobox, { target: { value: "go to" } });
    expect(optionNames()).toEqual(["Go to Approvals", "Go to Settings"]);
    expect(screen.queryByRole("option", { name: "Go to Contracts" })).toBeNull();
    fireEvent.keyDown(combobox, { key: "ArrowUp" });
    expect(combobox.getAttribute("aria-activedescendant")).toBe(
      screen.getByRole("option", { name: "Go to Settings" }).id,
    );

    fireEvent.change(combobox, { target: { value: "contracts" } });
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(combobox.getAttribute("aria-expanded")).toBe("false");
    // A holder of `contract.read` searches the records too: the sentence is the one of a search
    // that found nothing (SCREENS §1.4), once that search has answered.
    expect(await screen.findByText(NO_MATCHES("contracts"))).toBeTruthy();
    expect(world.searches).toEqual([{ q: "contracts", limit: "8" }]);
  });

  it("Theme: Dark sets data-theme, stores erev.theme and sends PATCH /me/preferences", async () => {
    const bodies: unknown[] = [];
    server.use(
      http.patch(apiUrl("/api/v1/me/preferences"), async ({ request }) => {
        bodies.push(await request.json());
        return HttpResponse.json({ preferences: { ...signedInMe().preferences, theme: "DARK" } });
      }),
    );
    renderPalette();
    modK(document.body);
    const combobox = screen.getByRole("combobox");
    fireEvent.change(combobox, { target: { value: "Theme: Dark" } });
    expect(optionNames()).toEqual(["Theme: Dark"]);
    fireEvent.keyDown(combobox, { key: "Enter" });
    expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
    expect(window.localStorage.getItem("erev.theme")).toBe("dark");
    expect(screen.queryByRole("dialog", { name: "Command palette" })).toBeNull();
    await waitFor(() => {
      expect(bodies).toEqual([{ theme: "DARK" }]);
    });
  });

  it("Esc clears the query, a second Esc closes, and focus returns to the prior element", () => {
    renderPalette();
    const prior = screen.getByRole("textbox", { name: "Quick filter" });
    act(() => {
      prior.focus();
    });
    modK(prior);
    const combobox = screen.getByRole("combobox");
    fireEvent.change(combobox, { target: { value: "appr" } });
    fireEvent.keyDown(combobox, { key: "Escape" });
    expect((combobox as HTMLInputElement).value).toBe("");
    expect(screen.getByRole("dialog", { name: "Command palette" })).toBeTruthy();
    fireEvent.keyDown(combobox, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Command palette" })).toBeNull();
    expect(document.activeElement).toBe(prior);
  });

  it("the search trigger opens the palette and Enter on Go to Approvals opens the route", async () => {
    const { router } = renderPalette();
    fireEvent.click(screen.getByRole("button", { name: "Search or run a command" }));
    const combobox = screen.getByRole("combobox");
    fireEvent.change(combobox, { target: { value: "approvals" } });
    fireEvent.keyDown(combobox, { key: "Enter" });
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/approvals");
    });
    expect(screen.queryByRole("dialog", { name: "Command palette" })).toBeNull();
  });
});

describe("SF-24 record search (BUILD_SPEC CTR-28)", () => {
  it("builds routes from scope and id", async () => {
    // SCREENS §1.4: a contract opens its Obligations tab; an invoice the Billing tab of the contract
    // its `href` names; a customer its page; a journal run its page.
    const routes: readonly (readonly [text: string, label: string, route: string])[] = [
      ["SF-ORD", K01, `/contracts/${K01_ID}/obligations`],
      ["SF-ORD", INVOICE, `/contracts/${K01_ID}/billing`],
      ["pellworth", CUSTOMER, `/settings/customers/${PELLWORTH_ID}`],
      ["JR-0001", RUN, `/journals/runs/${RUN_ID}`],
    ];
    for (const [text, label, route] of routes) {
      const { router } = renderPalette();
      openAndType(text);
      const option = await screen.findByRole("option", { name: label });
      // One search for the text, every scope, eight rows a scope.
      expect(world.searches.at(-1)).toEqual({ q: text, limit: "8" });
      fireEvent.mouseDown(option);
      await waitFor(() => {
        expect(router.state.location.pathname).toBe(route);
      });
      expect(router.state.location.search).toBe("");
      expect(screen.queryByRole("dialog", { name: "Command palette" })).toBeNull();
      cleanup();
    }
  });

  it("lists the found records a scope, in E-120 order, ahead of Show all results, pages and commands", async () => {
    renderPalette();
    const combobox = openAndType("SF-ORD");
    await screen.findByRole("option", { name: K01 });
    expect(optionLabels()).toEqual([
      K01,
      K02,
      CUSTOMER,
      INVOICE,
      OBLIGATION,
      OTHER_OBLIGATION,
      "Show all results",
    ]);
    // A scope that found nothing has no group: no journal run matches "SF-ORD".
    expect(groupNames()).toEqual(["Contracts", "Customers", "Invoices", "Obligations"]);
    // No page or command matches "SF-ORD": the first record is the active option.
    expect(activeLabel()).toBe(K01);
    expect(announce).toHaveBeenLastCalledWith("6 results", "polite");

    // DS-CMP-04: the word beginnings a term matches stand in weight 600, in both texts; a chip
    // shows the status, and none where the scope has no status or the literal shows none.
    const row = screen.getByRole("option", { name: INVOICE });
    expect(Array.from(row.querySelectorAll(".font-semibold"), (part) => part.textContent)).toEqual([
      "SF",
      "ORD",
    ]);
    expect(row.querySelector("[data-tone]")).toBeNull();
    const contract = screen.getByRole("option", { name: K02 });
    expect(contract.querySelector("[data-tone]")?.textContent).toBe("Pending approval");
    expect(
      screen.getByRole("option", { name: OTHER_OBLIGATION }).querySelector("[data-tone]"),
    ).toBeNull();

    // Down wraps from the last option to the first; Up from the first to the last.
    fireEvent.keyDown(combobox, { key: "ArrowUp" });
    expect(activeLabel()).toBe("Show all results");
    fireEvent.keyDown(combobox, { key: "ArrowDown" });
    expect(activeLabel()).toBe(K01);

    // A journal run reads its number, its period and entity, and the chip of its state.
    fireEvent.change(combobox, { target: { value: "FY2026" } });
    await screen.findByRole("option", { name: RUN });
    expect(optionLabels()).toEqual([RUN, "Show all results"]);
    expect(groupNames()).toEqual(["Journals"]);
  });

  it("record search starts at two characters with a letter or digit, 120 ms after the last key", async () => {
    renderPalette();
    const combobox = openAndType("S");
    await new Promise((resolve) => setTimeout(resolve, SEARCH_DEBOUNCE_MS + 80));
    fireEvent.change(combobox, { target: { value: "--" } });
    await new Promise((resolve) => setTimeout(resolve, SEARCH_DEBOUNCE_MS + 80));
    expect(world.searches).toEqual([]);
    expect(screen.queryByTestId("SF-24-searching")).toBeNull();

    // Three keys inside 120 ms: one search, for the text as it stands.
    fireEvent.change(combobox, { target: { value: "SF" } });
    fireEvent.change(combobox, { target: { value: "SF-" } });
    fireEvent.change(combobox, { target: { value: "  SF-ORD-1000  " } });
    expect(screen.getByTestId("SF-24-searching")).toBeTruthy();
    await screen.findByRole("option", { name: K01 });
    expect(world.searches).toEqual([{ q: "SF-ORD-1000", limit: "8" }]);
    expect(screen.queryByTestId("SF-24-searching")).toBeNull();
    // DS-CMP-04 names the wait; a test that slept less than it would fail on a slow run.
    expect(SEARCH_DEBOUNCE_MS).toBe(120);

    // A longer text is searched by its first 200 characters, the most the route takes.
    fireEvent.change(combobox, { target: { value: `SF-ORD ${"x".repeat(250)}` } });
    await waitFor(() => {
      expect(world.searches).toHaveLength(2);
    });
    expect(world.searches[1]?.q).toBe(`SF-ORD ${"x".repeat(193)}`);
  });

  it("a scope chip sends scope and lists that scope alone; Pages and Commands search nothing", async () => {
    const { router } = renderPalette();
    openAndType("SF-ORD");
    await screen.findByRole("option", { name: K01 });
    const chips = screen.getByRole("radiogroup", { name: "Search scope" });
    expect(
      within(chips)
        .getAllByRole("radio")
        .map((chip) => chip.textContent),
    ).toEqual([
      "All",
      "Contracts",
      "Customers",
      "Invoices",
      "Obligations",
      "Journals",
      "Pages",
      "Commands",
    ]);
    expect(within(chips).getByRole("radio", { name: "All" }).getAttribute("aria-checked")).toBe(
      "true",
    );

    fireEvent.click(within(chips).getByRole("radio", { name: "Contracts" }));
    await waitFor(() => {
      expect(world.searches.at(-1)).toEqual({ q: "SF-ORD", limit: "8", scope: "contracts" });
    });
    await waitFor(() => {
      expect(optionLabels()).toEqual([K01, K02, "Show all results"]);
    });

    // Under a scope of records a text that is not searched says what is missing.
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "S" } });
    expect(screen.getByText("Type at least 2 characters to search.")).toBeTruthy();

    // Left and Right move through the chips and choose; Pages lists the pages alone.
    const sent = world.searches.length;
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "se" } });
    const contracts = within(chips).getByRole("radio", { name: "Contracts" });
    act(() => {
      contracts.focus();
    });
    fireEvent.keyDown(contracts, { key: "ArrowLeft" });
    expect(document.activeElement).toBe(within(chips).getByRole("radio", { name: "All" }));
    fireEvent.keyDown(document.activeElement ?? contracts, { key: "ArrowLeft" });
    expect(
      within(chips).getByRole("radio", { name: "Commands" }).getAttribute("aria-checked"),
    ).toBe("true");
    fireEvent.keyDown(document.activeElement ?? contracts, { key: "ArrowLeft" });
    expect(optionLabels()).toEqual(["Go to Settings"]);
    expect(groupNames()).toEqual(["Pages"]);

    // "Show all results" under a scope chip opens the results page under that scope.
    fireEvent.click(within(chips).getByRole("radio", { name: "Contracts" }));
    fireEvent.change(screen.getByRole("combobox"), { target: { value: "SF-ORD" } });
    fireEvent.mouseDown(await screen.findByRole("option", { name: "Show all results" }));
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/search");
    });
    // The colon is plain: the page's filter codec reads the operator up to it.
    expect(router.state.location.search).toBe("?q=SF-ORD&f.scope=is:contracts");
    // "se" under Pages and Commands was never a search.
    expect(world.searches.slice(sent).every((search) => search.q !== "se")).toBe(true);
  });

  it("Show all results opens the results page for the text, and Mod Enter opens a record in a new tab", async () => {
    const opened = vi.spyOn(window, "open").mockReturnValue(null);
    const { router } = renderPalette();
    const combobox = openAndType("SF-ORD");
    await screen.findByRole("option", { name: K01 });

    fireEvent.keyDown(combobox, { key: "ArrowDown" });
    expect(activeLabel()).toBe(K02);
    fireEvent.keyDown(combobox, { key: "Enter", metaKey: true });
    expect(opened).toHaveBeenCalledWith(`/contracts/${K02_ID}/obligations`, "_blank", "noopener");
    // The palette stays open over its page.
    expect(screen.getByRole("dialog", { name: "Command palette" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/home");
    // A press with Command or Control does the same.
    fireEvent.mouseDown(screen.getByRole("option", { name: K01 }), { ctrlKey: true });
    expect(opened).toHaveBeenLastCalledWith(
      `/contracts/${K01_ID}/obligations`,
      "_blank",
      "noopener",
    );
    expect(screen.getByRole("dialog", { name: "Command palette" })).toBeTruthy();
    expect(router.state.location.pathname).toBe("/home");

    fireEvent.keyDown(combobox, { key: "ArrowUp" });
    fireEvent.keyDown(combobox, { key: "ArrowUp" });
    expect(activeLabel()).toBe("Show all results");
    fireEvent.keyDown(combobox, { key: "Enter" });
    await waitFor(() => {
      expect(router.state.location.pathname).toBe("/search");
    });
    expect(router.state.location.search).toBe("?q=SF-ORD");
    expect(screen.queryByRole("dialog", { name: "Command palette" })).toBeNull();
  });

  it("while an answer is on its way the rows before stay with the running mark; then no matches, then unavailable", async () => {
    renderPalette();
    const combobox = openAndType("SF-ORD");
    await screen.findByRole("option", { name: K01 });

    // DS-CMP-04 "loading": the rows of the answer before remain, and none of them is the active
    // option — the member did not ask for them with this text.
    const [held, release] = gate();
    world.hold = held;
    fireEvent.change(combobox, { target: { value: "SF-ORD-10002" } });
    await waitFor(() => {
      expect(world.searches.at(-1)).toEqual({ q: "SF-ORD-10002", limit: "8" });
    });
    expect(screen.getByTestId("SF-24-searching")).toBeTruthy();
    expect(screen.getByRole("listbox").getAttribute("aria-busy")).toBe("true");
    expect(optionLabels()).toContain(K01);
    expect(activeLabel()).toBeNull();
    release();
    world.hold = null;
    await waitFor(() => {
      expect(optionLabels()).toEqual([K02, OTHER_OBLIGATION, "Show all results"]);
    });
    expect(screen.queryByTestId("SF-24-searching")).toBeNull();
    expect(activeLabel()).toBe(K02);

    // No results (SCREENS §1.4): the sentence, once the search has answered.
    fireEvent.change(combobox, { target: { value: "zz-nothing" } });
    expect(await screen.findByText(NO_MATCHES("zz-nothing"))).toBeTruthy();
    expect(screen.queryByRole("listbox")).toBeNull();

    // A search that fails: the sentence, and the pages and commands the text matches stay.
    world.failWith = 500;
    fireEvent.change(combobox, { target: { value: "sett" } });
    expect(
      await screen.findByText("Search is unavailable. Pages and commands still work."),
    ).toBeTruthy();
    expect(optionLabels()).toEqual(["Go to Settings"]);
    world.failWith = null;
  });

  it("without contract.read the palette sends no search and says nothing of records", async () => {
    renderPalette({ me: signedInMe({ permissions: ["report.run"] }) });
    const combobox = openAndType("SF-ORD");
    expect(combobox.getAttribute("placeholder")).toBe("Search pages and commands");
    expect(
      within(screen.getByRole("radiogroup", { name: "Search scope" }))
        .getAllByRole("radio")
        .map((chip) => chip.textContent),
    ).toEqual(["All", "Pages", "Commands"]);
    expect(screen.getByText('No pages or commands match "SF-ORD".')).toBeTruthy();
    await new Promise((resolve) => setTimeout(resolve, SEARCH_DEBOUNCE_MS + 80));
    expect(world.searches).toEqual([]);
    expect(screen.queryByText("Search is unavailable. Pages and commands still work.")).toBeNull();
    expect(screen.queryByTestId("SF-24-searching")).toBeNull();
    fireEvent.change(combobox, { target: { value: "sett" } });
    expect(optionLabels()).toEqual(["Go to Settings"]);
  });

  it("a search the API refuses for the session shows no records and no error line", async () => {
    // A session whose access changed under it (SCREENS §1.4 "As bound"): pages and commands alone.
    world.failWith = 403;
    renderPalette();
    openAndType("sett");
    await waitFor(() => {
      expect(world.searches).toHaveLength(1);
    });
    await waitFor(() => {
      expect(screen.queryByTestId("SF-24-searching")).toBeNull();
    });
    expect(optionLabels()).toEqual(["Go to Settings"]);
    expect(screen.queryByText("Search is unavailable. Pages and commands still work.")).toBeNull();
  });

  it("the contract of an obligation is read when its row becomes the active one, and Enter waits for the read", async () => {
    const { router } = renderPalette();
    const combobox = openAndType("SF-ORD");
    await screen.findByRole("option", { name: OBLIGATION });
    expect(world.obligationReads).toEqual([]);

    const [held, release] = gate();
    world.holdObligations = held;
    for (let index = 0; index < 4; index += 1) {
      fireEvent.keyDown(combobox, { key: "ArrowDown" });
    }
    expect(activeLabel()).toBe(OBLIGATION);
    await waitFor(() => {
      expect(world.obligationReads).toEqual([OBLIGATION_ID]);
    });

    // Enter before the read has answered: the palette waits, and opens the route once it has.
    fireEvent.keyDown(combobox, { key: "Enter" });
    expect(screen.getByTestId("SF-24-searching")).toBeTruthy();
    expect(router.state.location.pathname).toBe("/home");
    release();
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(
        `/contracts/${K01_ID}/obligations/${OBLIGATION_ID}`,
      );
    });
    expect(screen.queryByRole("dialog", { name: "Command palette" })).toBeNull();
    // One read: the Enter took the read the active row had started.
    expect(world.obligationReads).toEqual([OBLIGATION_ID]);
  });

  it("an obligation whose contract is read opens at once, in a new tab with Mod Enter; a read that fails says so", async () => {
    const opened = vi.spyOn(window, "open").mockReturnValue(null);
    const { queryClient } = renderPalette();
    const combobox = openAndType("SF-ORD");
    await screen.findByRole("option", { name: OBLIGATION });
    for (let index = 0; index < 4; index += 1) {
      fireEvent.keyDown(combobox, { key: "ArrowDown" });
    }
    await waitFor(() => {
      expect(queryClient.getQueryData(obligationContractKey(OBLIGATION_ID))).toBe(K01_ID);
    });
    // The read has answered: `Mod Enter` has the route in hand and opens the tab inside the key press.
    fireEvent.keyDown(combobox, { key: "Enter", ctrlKey: true });
    expect(opened).toHaveBeenCalledWith(
      `/contracts/${K01_ID}/obligations/${OBLIGATION_ID}`,
      "_blank",
      "noopener",
    );
    expect(world.obligationReads).toEqual([OBLIGATION_ID]);

    // The other obligation's contract cannot be read.
    world.contractOf = {};
    fireEvent.keyDown(combobox, { key: "ArrowDown" });
    expect(activeLabel()).toBe(OTHER_OBLIGATION);
    fireEvent.keyDown(combobox, { key: "Enter" });
    expect(await screen.findByText("Could not open SF-ORD-10002 · O1. Try again.")).toBeTruthy();
    expect(screen.getByRole("dialog", { name: "Command palette" })).toBeTruthy();
    expect(screen.queryByTestId("SF-24-searching")).toBeNull();
  });

  it("Enter before the answer waits for it and opens the first record; a page the text matches stays the active option", async () => {
    // The member pastes an order number and presses Enter at once.
    const [held, release] = gate();
    world.hold = held;
    const first = renderPalette();
    const combobox = openAndType("SF-ORD-10002");
    fireEvent.keyDown(combobox, { key: "Enter" });
    expect(first.router.state.location.pathname).toBe("/home");
    release();
    await waitFor(() => {
      expect(first.router.state.location.pathname).toBe(`/contracts/${K02_ID}/obligations`);
    });
    cleanup();

    // "sett" matches the page "Go to Settings": it is the active option before the records arrive
    // and after, so Enter opens what the member saw as active.
    world = serveSearch({
      customers: [
        {
          id: PELLWORTH_ID,
          primary: "SETTLE-01",
          secondary: "Settlement Services Ltd (Demo)",
          status: null,
          href: `/api/v1/customers/${PELLWORTH_ID}`,
        },
      ],
    });
    const second = renderPalette();
    const again = openAndType("sett");
    expect(activeLabel()).toBe("Go to Settings");
    await screen.findByRole("option", { name: "SETTLE-01, Settlement Services Ltd (Demo)" });
    expect(optionLabels()).toEqual([
      "SETTLE-01, Settlement Services Ltd (Demo)",
      "Show all results",
      "Go to Settings",
    ]);
    expect(activeLabel()).toBe("Go to Settings");
    fireEvent.keyDown(again, { key: "Enter" });
    await waitFor(() => {
      expect(second.router.state.location.pathname).toBe("/settings");
    });
  });

  it("an answer that comes after the palette has closed, or after its page has left, opens nothing", async () => {
    // docs/dev-guide.md DG-FE-03 (3): an awaited read opens its record for the palette that asked,
    // still open over the page it was opened on.
    const [held, release] = gate();
    world.holdObligations = held;
    const first = renderPalette();
    const combobox = openAndType("SF-ORD");
    await screen.findByRole("option", { name: OBLIGATION });
    fireEvent.mouseDown(screen.getByRole("option", { name: OBLIGATION }));
    await waitFor(() => {
      expect(world.obligationReads).toEqual([OBLIGATION_ID]);
    });
    fireEvent.keyDown(combobox, { key: "Escape" });
    fireEvent.keyDown(combobox, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Command palette" })).toBeNull();
    release();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(first.router.state.location.pathname).toBe("/home");
    cleanup();

    // The page under the open palette changes (the browser's Back): the answer opens nothing, and
    // the palette stays as it is.
    world = serveSearch();
    const [again, releaseAgain] = gate();
    world.holdObligations = again;
    const second = renderPalette();
    openAndType("SF-ORD");
    fireEvent.mouseDown(await screen.findByRole("option", { name: OBLIGATION }));
    await waitFor(() => {
      expect(world.obligationReads).toEqual([OBLIGATION_ID]);
    });
    await act(async () => {
      await second.router.navigate("/contracts");
    });
    releaseAgain();
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(second.router.state.location.pathname).toBe("/contracts");
    expect(screen.getByRole("dialog", { name: "Command palette" })).toBeTruthy();

    // An Enter that waits for the search is dropped the same way.
    const [slow, releaseSlow] = gate();
    world.hold = slow;
    const input = screen.getByRole("combobox");
    fireEvent.change(input, { target: { value: "SF-ORD-10002" } });
    fireEvent.keyDown(input, { key: "Enter" });
    await act(async () => {
      await second.router.navigate("/schedules");
    });
    releaseSlow();
    await screen.findByRole("option", { name: K02 });
    expect(second.router.state.location.pathname).toBe("/schedules");
  });

  it("a record whose route is not built is not listed, and Show all results needs the results route", async () => {
    // XR-14: the palette offers only what it can open.
    renderWithApp(
      <CommandPalette built={new Set(["/settings", RECORD_ROUTE_PATTERNS.customers])} />,
    );
    openAndType("SF-ORD");
    await screen.findByRole("option", { name: CUSTOMER });
    expect(optionLabels()).toEqual([CUSTOMER]);
  });
});
