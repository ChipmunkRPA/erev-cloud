// @vitest-environment jsdom
// DS-CMP-03 component (DESIGN_SYSTEM §7.1; SCREENS §1.3): the "Accounting context" group of three listbox
// segments, a disabled segment with its tooltip, and the polite change announcement. BR-UX-01 binding
// (BUILD_SPEC RFD-19; PRD BR-UX-01; SCREENS §1.3, SCR-URL-01 to SCR-URL-03): the defaults from
// `GET /entities`, `GET /books` and `GET /periods`, the stored choice, and the segments per screen.
// The stored choice is the user's (BR-UX-01), so its storage key names the user and the workspace
// (security review 2026-09-29, P3-12).
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { announce } from "../../lib/a11y/announce";
import { installMemoryStorage, renderWithApp, signedInMe, signedInSession } from "../../test/app";
import { apiUrl, installMswServer, server } from "../../test/msw";
import {
  AccountingContextPill,
  CONTEXT_STORAGE_PREFIX,
  ContextPill,
  contextOwner,
  type ContextPillProps,
  type ContextSegment,
  type ContextValue,
  contextStorageKey,
  disabledDimensions,
  periodMarker,
  resolveEntityBook,
  resolvePeriod,
} from "./ContextPill";

vi.mock("../../lib/a11y/announce", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/a11y/announce")>();
  return { ...actual, announce: vi.fn() };
});

installMswServer();
installMemoryStorage();

afterEach(() => {
  cleanup();
  vi.mocked(announce).mockClear();
});

const ENTITIES: ContextSegment = {
  value: "US01",
  options: [
    { value: "US01", label: "US01 · eRev Demo Inc.", spoken: "US01" },
    { value: "UK01", label: "UK01 · eRev Demo Ltd.", spoken: "UK01" },
  ],
};

const PERIODS: ContextSegment = {
  value: "FY2026-P09",
  options: [
    { value: "FY2026-P09", label: "Sep 2026", marker: "open", group: "FY2026" },
    { value: "FY2026-P10", label: "Oct 2026", marker: "open", group: "FY2026" },
  ],
};

const BOOKS: ContextSegment = {
  value: "ASC606",
  options: [
    { value: "ASC606", label: "ASC 606" },
    { value: "IFRS15", label: "IFRS 15" },
  ],
};

function renderPill(overrides: Partial<ContextPillProps> = {}) {
  const onChange = vi.fn<(next: ContextValue) => void>();
  render(
    <ContextPill
      entity={ENTITIES}
      period={PERIODS}
      book={BOOKS}
      onChange={onChange}
      {...overrides}
    />,
  );
  return onChange;
}

describe("DS-CMP-03 component", () => {
  it("is a group named Accounting context with three segment buttons that open listboxes", () => {
    renderPill();
    const group = screen.getByRole("group", { name: "Accounting context" });
    const segments = within(group).getAllByRole("button");
    expect(segments.map((segment) => segment.getAttribute("aria-label"))).toEqual([
      "Entity: US01 · eRev Demo Inc.",
      "Period: Sep 2026, open",
      "Book: ASC 606",
    ]);
    for (const segment of segments) {
      expect(segment.getAttribute("aria-haspopup")).toBe("listbox");
      expect(segment.getAttribute("aria-expanded")).toBe("false");
    }
  });

  it("a disabled segment has aria-disabled and the tooltip Not used on this page", () => {
    renderPill({ book: { ...BOOKS, disabled: true } });
    const book = screen.getByRole("button", { name: "Book: ASC 606" });
    expect(book.getAttribute("aria-disabled")).toBe("true");
    fireEvent.keyDown(document.body, { key: "Tab" });
    act(() => {
      book.focus();
    });
    const tooltip = screen.getByRole("tooltip");
    expect(tooltip.textContent).toBe("Not used on this page");
    expect(book.getAttribute("aria-describedby")).toBe(tooltip.id);
    fireEvent.click(book);
    expect(book.getAttribute("aria-expanded")).toBe("false");
    expect(screen.queryByRole("listbox")).toBeNull();
  });

  it("a change announces Context changed to <entity>, <period label>, <book label>", () => {
    const onChange = renderPill();
    const period = screen.getByRole("button", { name: "Period: Sep 2026, open" });
    fireEvent.click(period);
    expect(period.getAttribute("aria-expanded")).toBe("true");
    const listbox = screen.getByRole("listbox", { name: "Period: Sep 2026, open" });
    expect(document.activeElement).toBe(listbox);
    expect(
      within(listbox)
        .getAllByRole("option")
        .map((option) => option.textContent),
    ).toEqual(["Sep 2026", "Oct 2026"]);
    fireEvent.keyDown(listbox, { key: "ArrowDown" });
    fireEvent.keyDown(listbox, { key: "Enter" });
    expect(onChange).toHaveBeenCalledWith({ entity: "US01", period: "FY2026-P10", book: "ASC606" });
    expect(announce).toHaveBeenCalledWith("Context changed to US01, Oct 2026, ASC 606", "polite");
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(document.activeElement).toBe(period);
  });

  it("Esc closes a selector without a change and returns focus to its segment", () => {
    const onChange = renderPill();
    const entity = screen.getByRole("button", { name: "Entity: US01 · eRev Demo Inc." });
    fireEvent.click(entity);
    fireEvent.keyDown(screen.getByRole("listbox"), { key: "Escape" });
    expect(screen.queryByRole("listbox")).toBeNull();
    expect(document.activeElement).toBe(entity);
    expect(onChange).not.toHaveBeenCalled();
    expect(announce).not.toHaveBeenCalled();
  });
});

const TENANT_ID = "0b6f3e2d-1c4a-4b8e-9d7f-6a5c4b3e2d1f";

function entityRow(code: string, name: string, books: readonly string[]) {
  return {
    id: `id-${code}`,
    code,
    name,
    is_active: true,
    books: books.map((book_code) => ({ book_code, is_enabled: true })),
  };
}

const ENTITY_ROWS = [
  entityRow("AVM-US", "Avenmoor Inc.", ["ASC606"]),
  entityRow("AVM-DE", "Avenmoor GmbH", ["ASC606"]),
  entityRow("AVM-UK", "Avenmoor Ltd", ["ASC606", "IFRS15"]),
];

const BOOK_ROWS = [
  { code: "IFRS15", is_primary: false, is_enabled: true },
  { code: "ASC606", is_primary: true, is_enabled: true },
  { code: "LEGACY", is_primary: false, is_enabled: false },
];

function periodRow(entity: string, month: number, state: string, isFirstOpen: boolean) {
  const two = String(month).padStart(2, "0");
  const last = month === 2 ? "28" : [4, 6, 9, 11].includes(month) ? "30" : "31";
  return {
    id: `${entity}-${two}`,
    entity: { id: `id-${entity}`, code: entity, name: entity },
    state,
    is_first_open: isFirstOpen,
    period: {
      period_key: `FY2026-P${two}`,
      fiscal_year: 2026,
      start_date: `2026-${two}-01`,
      end_date: `2026-${two}-${last}`,
    },
  };
}

/** `GET /entities`, `/books` and `/periods`; the periods of each entity and book, recorded by query. */
function serveStructure(periodQueries: string[]) {
  server.use(
    http.get(apiUrl("/api/v1/entities"), () =>
      HttpResponse.json({ items: ENTITY_ROWS, next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/books"), () =>
      HttpResponse.json({ items: BOOK_ROWS, next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/periods"), ({ request }) => {
      const url = new URL(request.url);
      const entity = url.searchParams.get("entity") ?? "";
      const book = url.searchParams.get("book") ?? "";
      periodQueries.push(`${entity}/${book}`);
      const items =
        entity === "AVM-UK" && book === "IFRS15"
          ? [
              periodRow(entity, 1, "closed", false),
              periodRow(entity, 2, "open", true),
              periodRow(entity, 3, "open", false),
            ]
          : [
              periodRow(entity, 1, "open", true),
              periodRow(entity, 2, "open", false),
              periodRow(entity, 3, "future", false),
            ];
      return HttpResponse.json({ items, next_cursor: null });
    }),
  );
}

const READER = signedInMe({ permissions: ["config.read", "contract.read"] });
// The key of READER's own choice in the workspace: user and workspace.
const STORAGE_KEY = contextStorageKey({ userId: READER.user.id, tenantId: TENANT_ID });

async function segmentNames(): Promise<(string | null)[]> {
  const group = await screen.findByRole("group", { name: "Accounting context" });
  return within(group)
    .getAllByRole("button")
    .map((segment) => segment.getAttribute("aria-label"));
}

describe("BR-UX-01", () => {
  it("defaults follow BR-UX-01", async () => {
    const queries: string[] = [];
    serveStructure(queries);
    renderWithApp(<AccountingContextPill />, { entry: "/settings/workspace", me: READER });

    // Without a stored choice: the first entity in code order, its primary book, its earliest open period.
    expect(await segmentNames()).toEqual([
      "Entity: AVM-DE · Avenmoor GmbH",
      "Period: Jan 2026, open",
      "Book: ASC 606",
    ]);
    expect(queries).toEqual(["AVM-DE/ASC606"]);
    cleanup();

    // A stored choice wins.
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ entity: "AVM-UK", period: "FY2026-P03", book: "IFRS15" }),
    );
    renderWithApp(<AccountingContextPill />, { entry: "/settings/workspace", me: READER });
    expect(await segmentNames()).toEqual([
      "Entity: AVM-UK · Avenmoor Ltd",
      "Period: Mar 2026, open",
      "Book: IFRS 15",
    ]);
    cleanup();

    // The URL parameters win over the stored choice; an invalid value falls through to the next source.
    const { router } = renderWithApp(<AccountingContextPill />, {
      entry: "/settings/workspace?entity=AVM-US&book=IFRS15",
      me: READER,
    });
    // AVM-US keeps no IFRS 15 book, so its primary book applies; the stored period key stays valid.
    expect(await segmentNames()).toEqual([
      "Entity: AVM-US · Avenmoor Inc.",
      "Period: Mar 2026",
      "Book: ASC 606",
    ]);
    expect(router.state.location.search).toBe("?entity=AVM-US&book=IFRS15");
  });

  it("a change stores the choice and replaces the context parameters; a new entity drops the period", async () => {
    serveStructure([]);
    const { router } = renderWithApp(<AccountingContextPill />, {
      entry: "/settings/workspace",
      me: READER,
    });
    await segmentNames();
    fireEvent.click(screen.getByRole("button", { name: "Entity: AVM-DE · Avenmoor GmbH" }));
    const listbox = screen.getByRole("listbox", { name: "Entity: AVM-DE · Avenmoor GmbH" });
    expect(
      within(listbox)
        .getAllByRole("option")
        .map((option) => [option.textContent, option.getAttribute("aria-selected")]),
    ).toEqual([
      ["AVM-DE · Avenmoor GmbH", "true"],
      ["AVM-UK · Avenmoor Ltd", "false"],
      ["AVM-US · Avenmoor Inc.", "false"],
    ]);
    fireEvent.keyDown(listbox, { key: "ArrowDown" });
    fireEvent.keyDown(listbox, { key: "Enter" });

    await waitFor(() => {
      expect(router.state.location.search).toBe("?entity=AVM-UK&book=ASC606");
    });
    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "null")).toEqual({
      entity: "AVM-UK",
      period: null,
      book: "ASC606",
    });
    await waitFor(async () => {
      expect(await segmentNames()).toEqual([
        "Entity: AVM-UK · Avenmoor Ltd",
        "Period: Jan 2026, open",
        "Book: ASC 606",
      ]);
    });
  });

  it("the stored choice is the user's: another user's choice in the workspace is neither applied nor overwritten", async () => {
    serveStructure([]);
    expect(contextOwner(READER, signedInSession())).toEqual({
      userId: READER.user.id,
      tenantId: TENANT_ID,
    });
    expect(STORAGE_KEY).toBe(`${CONTEXT_STORAGE_PREFIX}${READER.user.id}.${TENANT_ID}`);
    // The person who used this browser before, in the same workspace, and the key of the
    // workspace alone that earlier builds wrote for whoever was signed in.
    const other = contextStorageKey({
      userId: "7a1c9e2b-4d6f-4a8b-9c0d-1e2f3a4b5c6d",
      tenantId: TENANT_ID,
    });
    const earlier = JSON.stringify({ entity: "AVM-UK", period: "FY2026-P03", book: "IFRS15" });
    window.localStorage.setItem(other, earlier);
    window.localStorage.setItem(`${CONTEXT_STORAGE_PREFIX}${TENANT_ID}`, earlier);

    const { router } = renderWithApp(<AccountingContextPill />, {
      entry: "/settings/workspace",
      me: READER,
    });
    // BR-UX-01 "if none": READER has no choice of their own, so the defaults apply.
    expect(await segmentNames()).toEqual([
      "Entity: AVM-DE · Avenmoor GmbH",
      "Period: Jan 2026, open",
      "Book: ASC 606",
    ]);

    fireEvent.click(screen.getByRole("button", { name: "Entity: AVM-DE · Avenmoor GmbH" }));
    const listbox = screen.getByRole("listbox", { name: "Entity: AVM-DE · Avenmoor GmbH" });
    fireEvent.keyDown(listbox, { key: "ArrowDown" });
    fireEvent.keyDown(listbox, { key: "ArrowDown" });
    fireEvent.keyDown(listbox, { key: "Enter" });
    await waitFor(() => {
      expect(router.state.location.search).toBe("?entity=AVM-US&book=ASC606");
    });
    expect(JSON.parse(window.localStorage.getItem(STORAGE_KEY) ?? "null")).toEqual({
      entity: "AVM-US",
      period: null,
      book: "ASC606",
    });
    expect(window.localStorage.getItem(other)).toBe(earlier);
    expect(window.localStorage.getItem(`${CONTEXT_STORAGE_PREFIX}${TENANT_ID}`)).toBe(earlier);
  });

  it("the stored choice is the workspace's: a sandbox copy of one membership id neither reads nor overwrites its source's", async () => {
    // A sandbox copy keeps the ids of the rows it copies (SCREENS_B §9.7 "The open workspace").
    const source = READER.memberships[0];
    if (source === undefined) {
      throw new Error("no membership");
    }
    const COPY_ID = "1c1c1c1c-1c1c-4c1c-8c1c-1c1c1c1c1c1c";
    const member = {
      ...READER,
      memberships: [
        source,
        {
          ...source,
          tenant: {
            ...source.tenant,
            id: COPY_ID,
            code: "sbx-avenmoor-rehearsal",
            display_name: "Avenmoor rehearsal",
            kind: "sandbox" as const,
            source_tenant_id: TENANT_ID,
            source_known_at: "2026-09-12T18:10:00Z",
          },
        },
      ],
    };
    const inCopy = signedInSession({
      active_tenant: {
        id: COPY_ID,
        code: "sbx-avenmoor-rehearsal",
        display_name: "Avenmoor rehearsal",
        kind: "sandbox",
      },
    });
    expect(contextOwner(member, signedInSession())?.tenantId).toBe(TENANT_ID);
    expect(contextOwner(member, inCopy)?.tenantId).toBe(COPY_ID);

    serveStructure([]);
    const inSource = JSON.stringify({ entity: "AVM-UK", period: null, book: "ASC606" });
    window.localStorage.setItem(STORAGE_KEY, inSource);
    const { router } = renderWithApp(<AccountingContextPill />, {
      entry: "/settings/workspace",
      me: member,
      session: inCopy,
    });
    // The copy holds no choice of its own: the defaults, not the source's AVM-UK.
    expect(await segmentNames()).toEqual([
      "Entity: AVM-DE · Avenmoor GmbH",
      "Period: Jan 2026, open",
      "Book: ASC 606",
    ]);
    fireEvent.click(screen.getByRole("button", { name: "Entity: AVM-DE · Avenmoor GmbH" }));
    const listbox = screen.getByRole("listbox", { name: "Entity: AVM-DE · Avenmoor GmbH" });
    fireEvent.keyDown(listbox, { key: "ArrowDown" });
    fireEvent.keyDown(listbox, { key: "ArrowDown" });
    fireEvent.keyDown(listbox, { key: "Enter" });
    await waitFor(() => {
      expect(router.state.location.search).toBe("?entity=AVM-US&book=ASC606");
    });
    const copyKey = contextStorageKey({ userId: READER.user.id, tenantId: COPY_ID });
    expect(JSON.parse(window.localStorage.getItem(copyKey) ?? "null")).toEqual({
      entity: "AVM-US",
      period: null,
      book: "ASC606",
    });
    expect(window.localStorage.getItem(STORAGE_KEY)).toBe(inSource);
  });

  it("renders nothing without config.read or a workspace", async () => {
    serveStructure([]);
    renderWithApp(<AccountingContextPill />, {
      me: signedInMe({ permissions: ["contract.read"] }),
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(screen.queryByRole("group", { name: "Accounting context" })).toBeNull();
  });

  it("SCREENS §1.3 segments per screen, E-04 markers and the period fallbacks", () => {
    expect(disabledDimensions("SF-10:new")).toEqual({ entity: false, period: true, book: true });
    expect(disabledDimensions("SF-11:exception")).toEqual({
      entity: false,
      period: false,
      book: true,
    });
    // SCREENS rev 1.20: the SF-12 lists filter by the Entity chip, never by the pill's entity (§15.3).
    for (const screenId of [
      "SF-12",
      "SF-12:request",
      "SF-12:delegations",
      "SF-13:revenue",
      "SF-15:customers",
      "SF-16",
      "SF-24:results",
    ]) {
      expect(disabledDimensions(screenId)).toEqual({ entity: true, period: true, book: true });
    }
    for (const screenId of ["SF-15:workspace", "SF-15:chart-of-accounts", "SF-03", null]) {
      expect(disabledDimensions(screenId)).toEqual({ entity: false, period: false, book: false });
    }
    expect(
      ["open", "reopened", "closing", "closed", "permanently_locked", "future"].map(periodMarker),
    ).toEqual(["open", "open", "soft-close", "locked", "locked", undefined]);

    const noOpen = [
      periodRow("AVM-DE", 1, "closed", false),
      periodRow("AVM-DE", 2, "closing", false),
      periodRow("AVM-DE", 3, "future", false),
    ];
    expect(resolvePeriod(noOpen, [])?.period.period_key).toBe("FY2026-P02");
    expect(
      resolvePeriod(noOpen, [{ period: "FY2026-P09" }, { period: "FY2026-P03" }])?.period
        .period_key,
    ).toBe("FY2026-P03");
    const withoutBooks = [{ ...entityRow("AVM-JP", "Avenmoor KK", []) }];
    expect(resolveEntityBook(withoutBooks, BOOK_ROWS, [])).toBeNull();
  });
});
