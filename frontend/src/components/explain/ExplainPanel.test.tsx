// @vitest-environment jsdom
// DS-CMP-15 (DESIGN_SYSTEM §7.4; REQ-UX-005; 04 §16.11): a trigger opens the docked panel with focus on
// the heading, Esc returns focus to the trigger, Alt+Left goes up the Back stack, and another calculation
// version in the response shows the changed banner. A list level (SCREENS §6.3, rev 1.21) shows the
// entries of a value the trace holds at no node of its own.
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import {
  createMemoryRouter,
  MemoryRouter,
  Outlet,
  RouterProvider,
  useLocation,
} from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "../../app/providers";
import type { VerifyOutcome } from "../../lib/api/queries/explain";
import { periodsKey } from "../../lib/api/queries/tenant";
import { registerCurrencies } from "../../lib/format";
import { apiUrl, installMswServer, server } from "../../test/msw";
import {
  COLLAPSED_STEPS,
  type Explanation,
  ExplainPanel,
  ExplainProvider,
  type VerifyExplanation,
} from "./ExplainPanel";
import { type ExplainList, ExplainTrigger } from "./ExplainTrigger";

installMswServer();

beforeAll(() => {
  registerCurrencies([{ code: "USD", minor_unit: 2 }]);
});

afterEach(() => {
  cleanup();
});

const EXPLANATION: Explanation = {
  calc_trace_id: "trace-7",
  engine_version: "1.0.0",
  root_node_id: "n-rec",
  nodes: [
    {
      id: "n-rec",
      measure: "revenue_to_date",
      value: "55440.00",
      currency: "USD",
      formula_id: "F-REC-RATABLE-DAILY",
      params: { elapsed_days: "139", term_days: "365" },
      rounding_residue: null,
      inputs: [
        { node_id: "n-alloc" },
        {
          ref_type: "contract_event",
          ref_id: "e-1",
          label: "Contract activated · 01 Jan 2026",
          href: "/contracts/c-1/activity",
        },
      ],
    },
    {
      id: "n-alloc",
      measure: "allocated_amount",
      value: "145584.00",
      currency: "USD",
      formula_id: "F-ALLOC-RELATIVE-SSP",
      params: {},
      rounding_residue: null,
      inputs: [{ node_id: "n-weight" }],
    },
    {
      id: "n-weight",
      measure: "ssp_weight",
      value: "0.400000000000000000",
      currency: null,
      formula_id: null,
      params: {},
      rounding_residue: null,
      inputs: [],
    },
  ],
  narrative: ["Recognized to date is the allocated amount times the elapsed share of the term."],
  history: [
    {
      contract_version_id: "cv-2",
      version_no: 2,
      known_at: "2026-09-01T10:00:00Z",
      value: "55440.00",
      delta: "1200.00",
      cause: "CONTRACT_MODIFIED",
      origin_period_key: null,
    },
  ],
  context: { as_of: "2026-09-30T23:59:59Z", known_at: "2026-09-13T08:00:00Z" },
  drill: { source_rows: [] },
};

const LABEL = "Recognized revenue · Sep 2026";

const MATCHING: VerifyOutcome = {
  result: { recomputed_value: "55440.00", stored_value: "55440.00", matches: true },
  reference: "req-7",
};

function renderExplain(
  calcTraceId = "trace-7",
  explanation = EXPLANATION,
  verify: VerifyExplanation = vi.fn(() => Promise.resolve(MATCHING)),
) {
  const load = vi.fn(() => Promise.resolve(explanation));
  render(
    <QueryClientProvider client={createQueryClient()}>
      <MemoryRouter>
        <ExplainProvider load={load} verify={verify}>
          <ExplainTrigger
            figureRef={{
              objectType: "obligation",
              id: "o-1",
              measure: "revenue_to_date",
              periodKey: "FY2026-P09",
              calcTraceId,
            }}
            label={LABEL}
            valueText="USD 55,440.00"
          >
            55,440.00
          </ExplainTrigger>
          <ExplainPanel />
        </ExplainProvider>
      </MemoryRouter>
    </QueryClientProvider>,
  );
  return { load, trigger: screen.getByRole("button", { name: `Explain ${LABEL}, USD 55,440.00` }) };
}

describe("DS-CMP-15", () => {
  it("opening from a trigger moves focus to the heading", async () => {
    const { load, trigger } = renderExplain();
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "e" });
    const heading = screen.getByRole("heading", { level: 2, name: LABEL });
    expect(document.activeElement).toBe(heading);
    const panel = screen.getByRole("complementary", { name: LABEL });
    // SCREENS §6.3: the formula id shows in Formula and in its calculation step.
    expect(await within(panel).findAllByText("F-REC-RATABLE-DAILY")).toHaveLength(2);
    expect(load).toHaveBeenCalledWith(expect.objectContaining({ measure: "revenue_to_date" }));
    for (const section of [
      "Formula",
      "Inputs",
      "Calculation steps",
      "Source records",
      "Versions",
      "History",
    ]) {
      expect(within(panel).getByRole("heading", { level: 3, name: section })).toBeTruthy();
    }
    expect(
      within(panel).getByRole("link", { name: "Contract activated · 01 Jan 2026" }),
    ).toBeTruthy();
  });

  it("Esc closes the panel and returns focus to the trigger", async () => {
    const { trigger } = renderExplain();
    fireEvent.click(trigger);
    const panel = screen.getByRole("complementary", { name: LABEL });
    await within(panel).findAllByText("F-REC-RATABLE-DAILY");
    fireEvent.keyDown(screen.getByRole("heading", { level: 2, name: LABEL }), { key: "Escape" });
    expect(screen.queryByRole("complementary")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("Alt+Left goes back one level with the Back control named Back to <parent figure>", async () => {
    const { trigger } = renderExplain();
    fireEvent.click(trigger);
    fireEvent.click(await screen.findByRole("button", { name: "Explain Allocated" }));
    const child = screen.getByRole("heading", { level: 2, name: "Allocated" });
    expect(document.activeElement).toBe(child);
    expect(screen.getByRole("button", { name: `Back to ${LABEL}` })).toBeTruthy();
    // A non-money input keeps its full stored precision.
    expect(screen.getByText("0.400000000000000000")).toBeTruthy();

    fireEvent.keyDown(child, { key: "ArrowLeft", altKey: true });
    const parent = screen.getByRole("heading", { level: 2, name: LABEL });
    expect(document.activeElement).toBe(parent);
    expect(screen.queryByRole("button", { name: /^Back to/ })).toBeNull();

    fireEvent.click(await screen.findByRole("button", { name: "Explain Allocated" }));
    fireEvent.click(screen.getByRole("button", { name: `Back to ${LABEL}` }));
    expect(screen.getByRole("heading", { level: 2, name: LABEL })).toBeTruthy();
  });

  // BUILD_SPEC CTR-26: opening an input pushes onto the Back stack; Esc closes and returns focus to the
  // trigger (DS-CMP-15).
  it("back stack and escape", async () => {
    const { trigger } = renderExplain();
    trigger.focus();
    fireEvent.click(trigger);
    const panel = screen.getByRole("complementary", { name: LABEL });
    expect(within(panel).queryByRole("navigation", { name: "Explanation path" })).toBeNull();

    fireEvent.click(await within(panel).findByRole("button", { name: "Explain Allocated" }));
    const child = screen.getByRole("heading", { level: 2, name: "Allocated" });
    const path = screen.getByRole("navigation", { name: "Explanation path" });
    expect(within(path).getAllByRole("listitem")).toHaveLength(2);
    expect(within(path).getByRole("button", { name: `Back to ${LABEL}` })).toBeTruthy();
    expect(within(path).getByText("Allocated").getAttribute("aria-current")).toBe("page");

    fireEvent.keyDown(child, { key: "Escape" });
    expect(screen.queryByRole("complementary")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  // BUILD_SPEC CTR-26 (SCREENS §6.4, J-16.3): a `matches = true` response renders the positive message.
  it("verify match message", async () => {
    const verify = vi.fn<VerifyExplanation>(() => Promise.resolve(MATCHING));
    const { trigger } = renderExplain("trace-7", EXPLANATION, verify);
    fireEvent.click(trigger);
    const panel = screen.getByRole("complementary", { name: LABEL });
    fireEvent.click(await within(panel).findByRole("button", { name: "Verify" }));
    expect(
      await within(panel).findByText("Recomputed from the stored trace: 55,440.00. Matches."),
    ).toBeTruthy();
    expect(verify).toHaveBeenCalledWith(
      expect.objectContaining({ measure: "revenue_to_date", periodKey: "FY2026-P09" }),
    );
    expect(within(panel).getByRole("link", { name: "Open calculation trace" })).toBeTruthy();
  });

  it("a response with another calculation version shows the changed banner", async () => {
    const { trigger } = renderExplain("trace-6");
    fireEvent.click(trigger);
    expect(
      await screen.findByText(
        "This figure changed after the page loaded. Refresh to see current figures.",
      ),
    ).toBeTruthy();
  });

  it("the same calculation version shows no changed banner", async () => {
    const { trigger } = renderExplain("trace-7");
    fireEvent.click(trigger);
    await screen.findAllByText("F-REC-RATABLE-DAILY");
    expect(screen.queryByText(/This figure changed after the page loaded/)).toBeNull();
  });

  it("traces longer than six steps collapse behind Show all <n> steps", async () => {
    const chain = Array.from({ length: COLLAPSED_STEPS + 2 }, (_, index) => ({
      id: `n-${String(index)}`,
      measure: `step_${String(index)}`,
      value: String(index),
      currency: null,
      formula_id: `F-${String(index)}`,
      params: {},
      rounding_residue: null,
      inputs: index === COLLAPSED_STEPS + 1 ? [] : [{ node_id: `n-${String(index + 1)}` }],
    }));
    const { trigger } = renderExplain("trace-7", {
      ...EXPLANATION,
      root_node_id: "n-0",
      nodes: chain,
    });
    fireEvent.click(trigger);
    const panel = screen.getByRole("complementary", { name: LABEL });
    const show = await within(panel).findByRole("button", { name: "Show all 8 steps" });
    const steps = within(panel).getByRole("heading", {
      level: 3,
      name: "Calculation steps",
    }).parentElement;
    expect(steps?.querySelectorAll("ol li")).toHaveLength(COLLAPSED_STEPS);
    fireEvent.click(show);
    expect(steps?.querySelectorAll("ol li")).toHaveLength(8);
  });
});

// DG-FE-05 rev 1.156 (item W-23): "Verify" is a command the panel sends outside the hook; its key is
// the panel's for the figure.
describe("Verify as a command", () => {
  it("a verification that gets no answer goes out under the same key on the second press, and a new press after its answer is a new command", async () => {
    const ID = "3a4b5c6d-7e8f-4a1b-9c2d-3e4f5a6b7c8d";
    const keys: (string | null)[] = [];
    server.use(
      http.post(
        apiUrl(`/api/v1/explain/obligation/${ID}/revenue_to_date/verify`),
        ({ request }) => {
          keys.push(request.headers.get("Idempotency-Key"));
          return keys.length === 1
            ? HttpResponse.error()
            : HttpResponse.json(MATCHING.result, { headers: { "X-Request-Id": "req-7" } });
        },
      ),
    );
    const load = vi.fn(() => Promise.resolve(EXPLANATION));
    render(
      <QueryClientProvider client={createQueryClient()}>
        <MemoryRouter>
          {/* No `verify` is given: the panel sends the API command itself. */}
          <ExplainProvider load={load}>
            <ExplainTrigger
              figureRef={{ objectType: "obligation", id: ID, measure: "revenue_to_date" }}
              label={LABEL}
              valueText="USD 55,440.00"
            >
              55,440.00
            </ExplainTrigger>
            <ExplainPanel />
          </ExplainProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: `Explain ${LABEL}, USD 55,440.00` }));
    const panel = screen.getByRole("complementary", { name: LABEL });
    const verify = await within(panel).findByRole("button", { name: "Verify" });

    fireEvent.click(verify);
    expect(await within(panel).findByText("The figure could not be verified.")).toBeTruthy();
    fireEvent.click(verify);
    expect(
      await within(panel).findByText("Recomputed from the stored trace: 55,440.00. Matches."),
    ).toBeTruthy();
    expect(keys[0]).toMatch(/^[0-9a-f-]{36}$/);
    expect(keys[1]).toBe(keys[0]);

    fireEvent.click(verify);
    await waitFor(() => expect(keys).toHaveLength(3));
    expect(keys[2]).not.toBe(keys[0]);
  });
});

// D-87 L6-4-Q-2: a figure opened from the `explain` URL parameter takes its period label from the
// calendar the context pill loads and has no context line.
describe("URL-opened figure", () => {
  const FIGURE = "obligation~3a4b5c6d-7e8f-4a1b-9c2d-3e4f5a6b7c8d~revenue_to_date~FY2026-P09";

  function renderFromUrl(withCalendar: boolean) {
    const queryClient = createQueryClient();
    if (withCalendar) {
      queryClient.setQueryData(periodsKey({ entity: "AVM-US", book: "ASC606" }), [
        {
          state: "open",
          period: {
            period_key: "FY2026-P09",
            name: "Sep 2026",
            fiscal_year: 2026,
            start_date: "2026-09-01",
            end_date: "2026-09-30",
          },
        },
      ]);
    }
    const load = vi.fn(() => Promise.resolve(EXPLANATION));
    render(
      <QueryClientProvider client={queryClient}>
        <MemoryRouter initialEntries={[`/contracts?entity=AVM-US&book=ASC606&explain=${FIGURE}`]}>
          <ExplainProvider load={load}>
            <ExplainPanel />
          </ExplainProvider>
        </MemoryRouter>
      </QueryClientProvider>,
    );
  }

  it("takes the period label from the context calendar and shows no context line", async () => {
    renderFromUrl(true);
    const panel = await screen.findByRole("complementary", {
      name: "Recognized to date · Sep 2026",
    });
    expect(within(panel).queryByText(/AVM-US|ASC 606/)).toBeNull();
  });

  it("keeps the fiscal label while the calendar is not loaded", async () => {
    renderFromUrl(false);
    expect(
      await screen.findByRole("complementary", { name: "Recognized to date · FY2026 P09" }),
    ).toBeTruthy();
  });
});

// SCREENS §6.3 list level (rev 1.21; supervisor ruling R-112 (h)): the contract's Recognized at the
// measured period is no node of the trace, so its cell opens the entries the API does explain.
describe("list level", () => {
  const NAME = "Recognized to date · Sep 2026";
  const ENTRY = "Recognized to date · O1 · Sep 2026";
  const LIST: ExplainList = {
    label: NAME,
    value: "35440.11",
    currency: "USD",
    context: "SF-ORD-10001 · ASC 606 · AVM-US",
    caption: "By obligation",
    columns: { entry: "Obligation", amount: "Recognized to date" },
    rows: [
      {
        id: "o-1",
        label: "O1 · AVM-PLAT-100",
        amount: "30000.00",
        currency: "USD",
        explain: {
          label: "Explain O1",
          request: {
            figure: {
              objectType: "obligation_version",
              id: "3a4b5c6d-7e8f-4a1b-9c2d-3e4f5a6b7c8d",
              measure: "revenue_cum",
              periodKey: "FY2026-P09",
            },
            label: ENTRY,
            context: "SF-ORD-10001 · O1 · ASC 606 · AVM-US",
          },
        },
      },
      // The API links no explanation for this entry: it has no button.
      { id: "o-2", label: "O2 · AVM-IMPL", amount: "5940.11", currency: "USD" },
    ],
    empty: "No obligations yet",
    intro: "The table shows what is recognized for each obligation.",
    notes: <p>The contract's figure is net of consideration payable released to date.</p>,
  };

  function Where() {
    const location = useLocation();
    return <output data-testid="where">{location.search}</output>;
  }

  function renderList(lists: Readonly<Record<string, ExplainList>> | undefined) {
    const load = vi.fn(() => Promise.resolve(EXPLANATION));
    const tree = (current: Readonly<Record<string, ExplainList>> | undefined) => (
      <QueryClientProvider client={client}>
        <MemoryRouter initialEntries={["/contracts/c-1/obligations?entity=AVM-US"]}>
          <ExplainProvider load={load} lists={current}>
            <ExplainTrigger list="recognized" label="Recognized" valueText="USD 35,440.11">
              35,440.11
            </ExplainTrigger>
            <ExplainPanel />
            <Where />
          </ExplainProvider>
        </MemoryRouter>
      </QueryClientProvider>
    );
    const client = createQueryClient();
    const view = render(tree(lists));
    return {
      load,
      trigger: screen.getByRole("button", { name: "Explain Recognized, USD 35,440.11" }),
      provide: (next: Readonly<Record<string, ExplainList>> | undefined) =>
        view.rerender(tree(next)),
    };
  }

  it("names the measure and its period, shows the value, the entries and the sentences, and offers no Verify, trace link or link to copy", () => {
    const { load, trigger } = renderList({ recognized: LIST });
    trigger.focus();
    fireEvent.keyDown(trigger, { key: "e" });
    const heading = screen.getByRole("heading", { level: 2, name: NAME });
    expect(document.activeElement).toBe(heading);
    const panel = screen.getByRole("complementary", { name: NAME });
    expect(within(panel).getByText(/^USD\s35,440\.11$/)).toBeTruthy();
    expect(within(panel).getByText("SF-ORD-10001 · ASC 606 · AVM-US")).toBeTruthy();

    expect(within(panel).getByRole("heading", { level: 3, name: "By obligation" })).toBeTruthy();
    const table = within(panel).getByRole("table", { name: "By obligation" });
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((cell) => cell.textContent),
    ).toEqual(["Obligation", "Recognized to date", "Explain"]);
    const rows = within(table).getAllByRole("row").slice(1);
    expect(
      rows.map((row) =>
        within(row)
          .getAllByRole("rowheader")
          .concat(within(row).getAllByRole("cell"))
          .map((cell) => cell.textContent?.replace(/\s/g, " ")),
      ),
    ).toEqual([
      // The third cell holds the entry's button (its name is also its tooltip), where the API links one.
      ["O1 · AVM-PLAT-100", "USD 30,000.00", "Explain O1"],
      ["O2 · AVM-IMPL", "USD 5,940.11", ""],
    ]);
    // No total row: the value above the table is the API's figure, and the panel adds no money.
    expect(rows).toHaveLength(2);
    expect(within(rows[0] as HTMLElement).getByRole("button", { name: "Explain O1" })).toBeTruthy();
    expect(within(rows[1] as HTMLElement).queryByRole("button")).toBeNull();
    expect(
      within(panel).getByText("The table shows what is recognized for each obligation."),
    ).toBeTruthy();
    expect(
      within(panel).getByText(
        "The contract's figure is net of consideration payable released to date.",
      ),
    ).toBeTruthy();

    // The list is no node of the trace and no figure of the `explain` parameter.
    expect(within(panel).queryByRole("button", { name: "Verify" })).toBeNull();
    expect(within(panel).queryByRole("link", { name: "Open calculation trace" })).toBeNull();
    expect(within(panel).queryByRole("button", { name: "Copy link" })).toBeNull();
    expect(load).not.toHaveBeenCalled();
    expect(screen.getByTestId("where").textContent).toBe("?entity=AVM-US");
  });

  it("Explain <entry> opens the entry's explanation on the Back stack, the URL names that figure, and Back returns to the list", async () => {
    const { load, trigger } = renderList({ recognized: LIST });
    fireEvent.click(trigger);
    fireEvent.click(screen.getByRole("button", { name: "Explain O1" }));

    const entry = screen.getByRole("heading", { level: 2, name: ENTRY });
    expect(document.activeElement).toBe(entry);
    const panel = screen.getByRole("complementary", { name: ENTRY });
    expect(within(panel).getByText("SF-ORD-10001 · O1 · ASC 606 · AVM-US")).toBeTruthy();
    expect(await within(panel).findByRole("button", { name: "Verify" })).toBeTruthy();
    expect(load).toHaveBeenCalledWith(
      expect.objectContaining({
        objectType: "obligation_version",
        measure: "revenue_cum",
        periodKey: "FY2026-P09",
      }),
    );
    const path = within(panel).getByRole("navigation", { name: "Explanation path" });
    expect(
      within(path)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual([NAME, `›${ENTRY}`]);
    expect(screen.getByTestId("where").textContent).toBe(
      "?entity=AVM-US&explain=obligation_version%7E3a4b5c6d-7e8f-4a1b-9c2d-3e4f5a6b7c8d%7Erevenue_cum%7EFY2026-P09",
    );

    fireEvent.click(within(path).getByRole("button", { name: `Back to ${NAME}` }));
    expect(document.activeElement).toBe(screen.getByRole("heading", { level: 2, name: NAME }));
    expect(screen.getByRole("table", { name: "By obligation" })).toBeTruthy();
    expect(screen.getByTestId("where").textContent).toBe("?entity=AVM-US");

    // Esc closes the list and returns focus to the cell that opened it.
    fireEvent.keyDown(screen.getByRole("heading", { level: 2, name: NAME }), { key: "Escape" });
    expect(screen.queryByRole("complementary")).toBeNull();
    expect(document.activeElement).toBe(trigger);
  });

  it("follows the host's read of the entries: a skeleton, the error with Retry, the empty line, then the rows", () => {
    const onRetry = vi.fn();
    const { trigger, provide } = renderList({ recognized: { ...LIST, rows: undefined } });
    fireEvent.click(trigger);
    const panel = screen.getByRole("complementary", { name: NAME });
    expect(within(panel).queryByRole("table")).toBeNull();
    expect(within(panel).getByText("Loading By obligation")).toBeTruthy();

    provide({
      recognized: {
        ...LIST,
        rows: undefined,
        error: { title: "Could not load obligations", onRetry },
      },
    });
    expect(within(panel).getByText("Could not load obligations")).toBeTruthy();
    fireEvent.click(within(panel).getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);

    provide({ recognized: { ...LIST, rows: [] } });
    expect(within(panel).getByText("No obligations yet")).toBeTruthy();
    expect(within(panel).queryByRole("table")).toBeNull();

    provide({ recognized: { ...LIST, value: "36000.00" } });
    expect(within(panel).getByRole("table", { name: "By obligation" })).toBeTruthy();
    expect(within(panel).getByText(/^USD\s36,000\.00$/)).toBeTruthy();
  });

  it("a new read of the same entries leaves the focus where the reader put it", () => {
    const { trigger, provide } = renderList({ recognized: LIST });
    fireEvent.click(trigger);
    const entry = screen.getByRole("button", { name: "Explain O1" });
    entry.focus();
    // The host provides the list again on every render of its own (a refetch, a job indicator).
    provide({ recognized: { ...LIST, rows: [...(LIST.rows ?? [])] } });
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Explain O1" }));
  });

  it("a list the host no longer provides is not shown", () => {
    const { trigger, provide } = renderList({ recognized: LIST });
    fireEvent.click(trigger);
    expect(screen.getByRole("complementary", { name: NAME })).toBeTruthy();
    provide(undefined);
    expect(screen.queryByRole("complementary")).toBeNull();
  });
});

// KIT-FILTER-LEAVING-2 (dev-guide DG-FE-03 rule (3), rev 1.230): the panel writes the figure into the
// address with the path it rendered. A figure opened from the page being left, after the router had
// moved on, took the member back to that page.
describe("a figure opened from a page that is leaving", () => {
  it("is not carried into the address, and the member stays on the page they went to", async () => {
    const load = vi.fn(() => Promise.resolve(EXPLANATION));
    const verify: VerifyExplanation = vi.fn(() => Promise.resolve(MATCHING));
    const router = createMemoryRouter(
      [
        {
          element: (
            <ExplainProvider load={load} verify={verify}>
              <Outlet />
              <ExplainPanel />
            </ExplainProvider>
          ),
          children: [
            {
              path: "/contracts",
              element: (
                <ExplainTrigger
                  figureRef={{
                    objectType: "obligation",
                    id: "o-1",
                    measure: "revenue_to_date",
                    periodKey: "FY2026-P09",
                    calcTraceId: "trace-7",
                  }}
                  label={LABEL}
                  valueText="USD 55,440.00"
                >
                  55,440.00
                </ExplainTrigger>
              ),
            },
            { path: "/schedules", element: <h1>Schedules</h1> },
          ],
        },
      ],
      { initialEntries: ["/contracts?entity=AVM-US"] },
    );
    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>,
    );
    const trigger = await screen.findByRole("button", {
      name: `Explain ${LABEL}, USD 55,440.00`,
    });

    // The router holds the next page; React renders it a task later.
    await router.navigate("/schedules?entity=AVM-US&book=ASC606");
    expect(document.body.contains(trigger)).toBe(true);
    fireEvent.click(trigger);

    expect(await screen.findByRole("heading", { level: 1, name: "Schedules" })).toBeTruthy();
    expect(`${router.state.location.pathname}${router.state.location.search}`).toBe(
      "/schedules?entity=AVM-US&book=ASC606",
    );
    expect(screen.queryByRole("complementary", { name: LABEL })).toBeNull();
  });
});
