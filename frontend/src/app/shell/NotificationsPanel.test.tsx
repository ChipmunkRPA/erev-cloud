// @vitest-environment jsdom
// SF-21 (SCREENS §1.2; DESIGN_SYSTEM DS-CMP-05; 04 API-R-03, §16.12): the bell name from
// X-Erev-Total-Count, the badge refresh rules, "Mark all as read", selecting an item, the empty panel, the
// keyboard rules and the single announcement of a new approval request.
import { notifyManager } from "@tanstack/react-query";
import { act, cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";

import { announce } from "../../lib/a11y/announce";
import { useCommand } from "../../lib/api/commands";
import { type Notification, unreadBadgeKey } from "../../lib/api/queries/notifications";
import { formatNumber } from "../../lib/format";
import { renderWithApp } from "../../test/app";
import { apiUrl, installMswServer, server } from "../../test/msw";
import { badgeText, NotificationsPanel } from "./NotificationsPanel";

vi.mock("../../lib/a11y/announce", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/a11y/announce")>();
  return { ...actual, announce: vi.fn() };
});

installMswServer();

function setVisibility(state: DocumentVisibilityState): void {
  Object.defineProperty(document, "visibilityState", { configurable: true, get: () => state });
}

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  vi.mocked(announce).mockClear();
  setVisibility("visible");
  notifyManager.setScheduler((callback) => {
    setTimeout(callback, 0);
  });
});

const EMPTY =
  "You are up to date. Approval requests and decisions, period changes, close blockers, failures and assigned exceptions appear here.";

function notification(index: number, overrides: Partial<Notification> = {}): Notification {
  return {
    id: `6f1e2d3c-4b5a-4c6d-8e7f-00000000000${String(index)}`,
    kind: "APPROVAL_ASSIGNED",
    title: `Approval needed: SSP book version US-LIST 2026-H${String(index)}`,
    body: "SSP book version US-LIST 2026-H2 awaits your decision.",
    link_path: `/approvals/2a3b4c5d-6e7f-4a8b-9c0d-1e2f3a4b5c6${String(index)}`,
    subject_type: "ssp_book_version",
    subject_id: null,
    read_at: null,
    created_at: `2026-09-13T09:1${String(index)}:00Z`,
    ...overrides,
  };
}

interface Served {
  total: number;
  unread: readonly Notification[];
  all: readonly Notification[] | null;
  readonly badgeCalls: URLSearchParams[];
  readonly listCalls: URLSearchParams[];
}

function serveNotifications(total: number, unread: readonly Notification[]): Served {
  const served: Served = { total, unread, all: null, badgeCalls: [], listCalls: [] };
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), ({ request }) => {
      const params = new URL(request.url).searchParams;
      if (params.get("count") === "true") {
        served.badgeCalls.push(params);
        return HttpResponse.json(
          { items: served.unread.slice(0, 1), next_cursor: null },
          { headers: { "X-Erev-Total-Count": String(served.total) } },
        );
      }
      served.listCalls.push(params);
      const items = params.get("unread") === "true" ? served.unread : (served.all ?? served.unread);
      return HttpResponse.json({ items, next_cursor: null });
    }),
  );
  return served;
}

function ProbeCommand() {
  const { submit } = useCommand({ method: "POST", path: "/api/v1/probe" });
  return (
    <button
      type="button"
      onClick={() => {
        void submit({});
      }}
    >
      Run probe
    </button>
  );
}

describe("SF-21", () => {
  it("with X-Erev-Total-Count: 3 the bell is named Notifications, 3 unread", async () => {
    const served = serveNotifications(3, [notification(3), notification(2), notification(1)]);
    renderWithApp(<NotificationsPanel built={new Set()} />, { badge: null });
    const bell = await screen.findByRole("button", { name: "Notifications, 3 unread" });
    expect(bell.getAttribute("aria-haspopup")).toBe("dialog");
    expect(bell.getAttribute("aria-expanded")).toBe("false");
    expect(within(bell).getByText("3")).toBeTruthy();
    const params = served.badgeCalls[0];
    expect(params === undefined ? null : Object.fromEntries(params)).toEqual({
      unread: "true",
      count: "true",
      limit: "1",
    });
  });

  it("the badge shows the count up to 99, then 99+; a capped total keeps its figure in the name", () => {
    expect(badgeText(3, false)).toBe(formatNumber(3));
    expect(badgeText(99, false)).toBe(formatNumber(99));
    expect(badgeText(120, false)).toBe(`${formatNumber(99)}+`);
    expect(badgeText(100000, true)).toBe(`${formatNumber(99)}+`);

    renderWithApp(<NotificationsPanel built={new Set()} />, {
      badge: { count: 100000, capped: true, newest: null },
    });
    const bell = screen.getByRole("button", {
      name: `Notifications, ${formatNumber(100000)}+ unread`,
    });
    expect(within(bell).getByText(`${formatNumber(99)}+`)).toBeTruthy();
  });

  it("the badge refetches every 60 seconds while visible and after every successful command", async () => {
    notifyManager.setScheduler((callback) => {
      callback();
    });
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const served = serveNotifications(1, [notification(1)]);
    server.use(http.post(apiUrl("/api/v1/probe"), () => HttpResponse.json({ ok: true })));
    renderWithApp(
      <>
        <NotificationsPanel built={new Set()} />
        <ProbeCommand />
      </>,
      { badge: null },
    );
    await waitFor(() => {
      expect(served.badgeCalls).toHaveLength(1);
    });

    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    await waitFor(() => {
      expect(served.badgeCalls).toHaveLength(2);
    });

    setVisibility("hidden");
    await act(async () => {
      await vi.advanceTimersByTimeAsync(120_000);
    });
    expect(served.badgeCalls).toHaveLength(2);
    setVisibility("visible");

    fireEvent.click(screen.getByRole("button", { name: "Run probe" }));
    await waitFor(() => {
      expect(served.badgeCalls).toHaveLength(3);
    });
  });

  it("Mark all as read sends before = the newest loaded created_at, refetches and announces", async () => {
    const served = serveNotifications(3, [notification(3), notification(2), notification(1)]);
    const bodies: unknown[] = [];
    server.use(
      http.post(apiUrl("/api/v1/me/notifications/read-all"), async ({ request }) => {
        bodies.push(await request.json());
        served.total = 0;
        served.unread = [];
        return HttpResponse.json({ marked: 3 });
      }),
    );
    renderWithApp(<NotificationsPanel built={new Set()} />, { badge: null });
    fireEvent.click(await screen.findByRole("button", { name: "Notifications, 3 unread" }));
    const panel = screen.getByRole("dialog", { name: "Notifications" });
    expect(within(panel).getByRole("tab", { name: "Unread" }).getAttribute("aria-selected")).toBe(
      "true",
    );
    fireEvent.click(await within(panel).findByRole("button", { name: "Mark all as read" }));

    await waitFor(() => {
      expect(announce).toHaveBeenCalledWith("Marked 3 notifications as read", "polite");
    });
    expect(bodies).toEqual([{ before: "2026-09-13T09:13:00Z" }]);
    expect(await screen.findByRole("button", { name: "Notifications" })).toBeTruthy();
    expect(await within(panel).findByText(EMPTY)).toBeTruthy();
    expect(within(panel).queryByRole("button", { name: "Mark all as read" })).toBeNull();
  });

  it("selecting an item navigates to its link_path and sends POST /me/notifications/{id}/read", async () => {
    const item = notification(1);
    serveNotifications(1, [item]);
    const reads: string[] = [];
    server.use(
      http.post(apiUrl("/api/v1/me/notifications/:id/read"), ({ params }) => {
        reads.push(String(params.id));
        return HttpResponse.json({ ...item, read_at: "2026-09-13T09:20:00Z" });
      }),
    );
    const { router } = renderWithApp(<NotificationsPanel built={new Set()} />, { badge: null });
    fireEvent.click(await screen.findByRole("button", { name: "Notifications, 1 unread" }));
    const link = await screen.findByRole("link", { name: item.title });
    expect(screen.getByText("SSP book version US-LIST 2026-H2 awaits your decision.")).toBeTruthy();
    fireEvent.click(link);
    await waitFor(() => {
      expect(router.state.location.pathname).toBe(item.link_path);
    });
    await waitFor(() => {
      expect(reads).toEqual([item.id]);
    });
    expect(screen.queryByRole("dialog", { name: "Notifications" })).toBeNull();
  });

  it("the empty panel reads You are up to date", async () => {
    serveNotifications(0, []);
    renderWithApp(<NotificationsPanel built={new Set(["/settings/notifications"])} />, {
      badge: null,
    });
    fireEvent.click(screen.getByRole("button", { name: "Notifications" }));
    const panel = screen.getByRole("dialog", { name: "Notifications" });
    expect(await within(panel).findByText(EMPTY)).toBeTruthy();
    expect(within(panel).queryByRole("button", { name: "Mark all as read" })).toBeNull();
    expect(
      within(panel).getByRole("link", { name: "Notification preferences" }).getAttribute("href"),
    ).toBe("/settings/notifications");
  });

  it("Enter opens the panel at its first item and Esc returns focus to the bell", async () => {
    serveNotifications(2, [notification(2), notification(1)]);
    renderWithApp(<NotificationsPanel built={new Set()} />, { badge: null });
    const bell = await screen.findByRole("button", { name: "Notifications, 2 unread" });
    fireEvent.keyDown(bell, { key: "Enter" });
    expect(bell.getAttribute("aria-expanded")).toBe("true");
    const first = await screen.findByRole("link", { name: notification(2).title });
    await waitFor(() => {
      expect(document.activeElement).toBe(first);
    });
    fireEvent.keyDown(first, { key: "Escape" });
    expect(screen.queryByRole("dialog", { name: "Notifications" })).toBeNull();
    expect(document.activeElement).toBe(bell);
  });

  it("a new APPROVAL_ASSIGNED notification is announced once", async () => {
    const served = serveNotifications(1, [notification(1)]);
    const { queryClient } = renderWithApp(<NotificationsPanel built={new Set()} />, {
      badge: null,
    });
    await screen.findByRole("button", { name: "Notifications, 1 unread" });
    expect(announce).not.toHaveBeenCalled();

    served.total = 2;
    served.unread = [notification(2), notification(1)];
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: unreadBadgeKey() });
    });
    await screen.findByRole("button", { name: "Notifications, 2 unread" });
    await act(async () => {
      await queryClient.invalidateQueries({ queryKey: unreadBadgeKey() });
    });
    expect(vi.mocked(announce).mock.calls).toEqual([[notification(2).title, "polite"]]);
  });
});
