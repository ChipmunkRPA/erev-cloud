// @vitest-environment jsdom
// DS-CMP-13 (DESIGN_SYSTEM §7.3; SCREENS §0.5 SCR-URL-10, SCR-URL-21; APG Toolbar): filters are URL state,
// chips are removed with Backspace and the result count is announced, and unparseable links are cleaned.
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { createMemoryRouter, MemoryRouter, RouterProvider, useLocation } from "react-router";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

import { registerLiveRegions } from "../../lib/a11y/announce";
import { registerCurrencies } from "../../lib/format";
import { FilterBar, RESULT_ANNOUNCE_MS } from "./FilterBar";
import type { FilterField } from "./filters";

const FIELDS: readonly FilterField[] = [
  {
    name: "status",
    label: "Status",
    kind: "enum",
    operators: ["is", "in"],
    options: [
      { value: "DRAFT", label: "Draft" },
      { value: "PENDING_REVIEW", label: "Pending approval" },
      { value: "ACTIVE", label: "Active" },
      { value: "VOID", label: "Void" },
    ],
  },
  { name: "on_hold", label: "On hold", kind: "boolean", operators: ["is"] },
  {
    name: "transaction_price",
    label: "Transaction price",
    kind: "money",
    currency: "USD",
    operators: ["between", "gte", "lte"],
  },
];

beforeAll(() => {
  registerCurrencies([{ code: "USD", minor_unit: 2 }]);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function Probe() {
  return <output data-testid="search">{useLocation().search}</output>;
}

function renderBar(search: string) {
  const tree = (count: number) => (
    <MemoryRouter initialEntries={[`/contracts${search}`]}>
      <FilterBar
        fields={FIELDS}
        searchLabel="Search contracts"
        resultCount={count}
        resultLabel={(n) => `${String(n)} contracts`}
      />
      <Probe />
    </MemoryRouter>
  );
  const view = render(tree(12));
  return { setCount: (count: number) => view.rerender(tree(count)) };
}

function currentSearch(): string {
  return screen.getByTestId("search").textContent ?? "";
}

describe("DS-CMP-13", () => {
  it("applying Status is Draft or Pending approval writes f.status=in:DRAFT,PENDING_REVIEW", () => {
    renderBar("");
    const bar = screen.getByRole("toolbar", { name: "Filters" });

    fireEvent.click(within(bar).getByRole("button", { name: "Filter" }));
    fireEvent.click(
      within(screen.getByRole("dialog", { name: "Filter" })).getByRole("button", {
        name: "Status",
      }),
    );
    const editor = screen.getByRole("dialog", { name: "Status filter" });
    fireEvent.click(within(editor).getByRole("checkbox", { name: "Draft" }));
    fireEvent.click(within(editor).getByRole("checkbox", { name: "Pending approval" }));
    fireEvent.click(within(editor).getByRole("button", { name: "Apply" }));

    expect(currentSearch()).toBe("?f.status=in:DRAFT,PENDING_REVIEW");
    expect(screen.queryByRole("dialog")).toBeNull();
    const chip = within(bar).getByRole("button", {
      name: "Status is Draft or Pending approval, edit filter",
    });
    expect(chip.textContent).toBe("Status is Draft or Pending approval");
    expect(document.activeElement).toBe(chip);
  });

  it("a field that offers only `in` writes one chosen value as in:, the operator it offers", () => {
    // SF-13:control-rules "Kind" (SCREENS §11.1): `is:` would be dropped under SCR-URL-21.
    const fields: readonly FilterField[] = [
      {
        name: "kind",
        label: "Kind",
        kind: "enum",
        operators: ["in"],
        options: [
          { value: "APPROVAL_ROUTING", label: "Approval routing" },
          { value: "HOLD", label: "Holds" },
        ],
      },
    ];
    render(
      <MemoryRouter initialEntries={["/policies/control-rules"]}>
        <FilterBar fields={fields} resultCount={5} resultLabel={(n) => `${String(n)} rule sets`} />
        <Probe />
      </MemoryRouter>,
    );
    const bar = screen.getByRole("toolbar", { name: "Filters" });

    fireEvent.click(within(bar).getByRole("button", { name: "Filter" }));
    fireEvent.click(
      within(screen.getByRole("dialog", { name: "Filter" })).getByRole("button", { name: "Kind" }),
    );
    const editor = screen.getByRole("dialog", { name: "Kind filter" });
    fireEvent.click(within(editor).getByRole("checkbox", { name: "Holds" }));
    fireEvent.click(within(editor).getByRole("button", { name: "Apply" }));

    expect(currentSearch()).toBe("?f.kind=in:HOLD");
    expect(within(bar).getByRole("button", { name: "Kind is Holds, edit filter" })).toBeTruthy();
    expect(
      screen.queryByText("Some filters in the link were not recognised and were removed."),
    ).toBeNull();
  });

  it("truncates chip values after two items and rejects an empty selection inline", () => {
    renderBar("?f.status=in:DRAFT,VOID,ACTIVE,PENDING_REVIEW");
    const chip = screen.getByRole("button", { name: /, edit filter$/ });
    expect(chip.textContent).toBe("Status is Draft, Void +2");

    fireEvent.click(screen.getByRole("button", { name: "Filter" }));
    fireEvent.click(screen.getByRole("button", { name: "Transaction price" }));
    const editor = screen.getByRole("dialog", { name: "Transaction price filter" });
    fireEvent.click(within(editor).getByRole("button", { name: "Apply" }));
    expect(within(editor).getByText("Enter both values.")).toBeTruthy();
    expect(within(editor).getByRole("textbox", { name: "From" }).getAttribute("aria-invalid")).toBe(
      "true",
    );
    fireEvent.change(within(editor).getByRole("textbox", { name: "From" }), {
      target: { value: "1,000.5" },
    });
    fireEvent.change(within(editor).getByRole("textbox", { name: "To" }), {
      target: { value: "abc" },
    });
    fireEvent.click(within(editor).getByRole("button", { name: "Apply" }));
    expect(within(editor).getByText("Enter a number such as 1,234.56.")).toBeTruthy();
    expect(currentSearch()).toBe("?f.status=in:DRAFT,VOID,ACTIVE,PENDING_REVIEW");

    fireEvent.keyDown(editor, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(document.activeElement).toBe(screen.getByRole("button", { name: "Filter" }));
  });

  it("Backspace on a focused chip removes it and announces Filter removed. <n> <plural label>.", async () => {
    vi.useFakeTimers();
    const polite = vi.fn();
    const unregister = registerLiveRegions(polite, vi.fn());
    const { setCount } = renderBar("?f.status=is:DRAFT&f.on_hold=is:true");
    const chip = screen.getByRole("button", { name: "Status is Draft, edit filter" });
    chip.focus();

    fireEvent.keyDown(chip, { key: "ArrowRight" });
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Remove filter: Status" }),
    );
    fireEvent.keyDown(chip, { key: "Backspace" });

    expect(currentSearch()).toBe("?f.on_hold=is:true");
    expect(screen.queryByRole("button", { name: /^Status is/ })).toBeNull();
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "On hold is Yes, edit filter" }),
    );
    setCount(214);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(RESULT_ANNOUNCE_MS);
    });
    expect(polite).toHaveBeenCalledWith("Filter removed. 214 contracts.");
    unregister();
  });

  it("drops an unparseable f. value with the SCR-URL-21 banner", () => {
    renderBar("?f.status=is:NOPE&f.unknown=is:x&f.on_hold=is:true");

    expect(
      screen.getByText("Some filters in the link were not recognised and were removed."),
    ).toBeTruthy();
    expect(currentSearch()).toBe("?f.on_hold=is:true");
    expect(screen.getByRole("button", { name: "On hold is Yes, edit filter" })).toBeTruthy();
  });
});

// The bar under a data router, as the application runs it. The route loads, as the session route of
// the application does, so a navigation is on its way for a moment before the router holds its
// address; React renders that address a task later still.
async function renderInDataRouter(search: string) {
  const router = createMemoryRouter(
    [
      {
        path: "/contracts",
        loader: () => null,
        HydrateFallback: () => null,
        element: <FilterBar fields={FIELDS} searchLabel="Search contracts" />,
      },
    ],
    { initialEntries: [`/contracts${search}`] },
  );
  render(<RouterProvider router={router} />);
  const bar = await screen.findByRole("toolbar", { name: "Filters" });
  return { router, bar };
}

describe("KIT-FILTER-LEAVING-1 the bar writes from the router's own search (DG-FE-03 rev 1.215)", () => {
  it("a second chip removed while the first write is on its way does not put the first chip back", async () => {
    const { router, bar } = await renderInDataRouter(
      "?sort=-booked_at&f.status=is:DRAFT&f.on_hold=is:true",
    );
    const status = within(bar).getByRole("button", { name: "Remove filter: Status" });
    const onHold = within(bar).getByRole("button", { name: "Remove filter: On hold" });

    fireEvent.click(status);
    expect(router.state.navigation.state).toBe("loading");
    expect(router.state.location.search).toBe(
      "?sort=-booked_at&f.status=is:DRAFT&f.on_hold=is:true",
    );
    fireEvent.click(onHold);

    await waitFor(() => expect(router.state.navigation.state).toBe("idle"));
    expect(router.state.location.search).toBe("?sort=-booked_at");
  });

  it("a second chip removed after the router took the first write and before React rendered it does not put the first chip back", async () => {
    const { router, bar } = await renderInDataRouter(
      "?sort=-booked_at&f.status=is:DRAFT&f.on_hold=is:true",
    );
    const status = within(bar).getByRole("button", { name: "Remove filter: Status" });
    const onHold = within(bar).getByRole("button", { name: "Remove filter: On hold" });

    fireEvent.click(status);
    // Microtasks only: the router finishes the navigation, and React has had no task to render it in.
    for (let turn = 0; turn < 200 && router.state.navigation.state !== "idle"; turn += 1) {
      await Promise.resolve();
    }
    expect(router.state.location.search).toBe("?sort=-booked_at&f.on_hold=is:true");
    expect(document.body.contains(status)).toBe(true);
    fireEvent.click(onHold);

    await waitFor(() => expect(router.state.navigation.state).toBe("idle"));
    expect(router.state.location.search).toBe("?sort=-booked_at");
  });
});
