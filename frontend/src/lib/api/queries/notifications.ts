// In-app notifications of the caller (04 API-R-03, T-PLT-24; SCREENS §1.2 SF-21; DESIGN_SYSTEM
// DS-CMP-05). The badge reads `GET /me/notifications?unread=true&count=true&limit=1` and refetches
// every 60 seconds while the page is visible, on window focus and after every successful command;
// the panel tabs read 50 items; "Mark all as read" and selecting an item are commands.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";

import { onCommandSucceeded, useCommand } from "../commands";
import { fetchListPage } from "../lists";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";

export type Notification = components["schemas"]["NotificationOut"];
export type NotificationKind = components["schemas"]["NotificationKind"];
type ReadAllOut = components["schemas"]["NotificationReadAllOut"];

export const NOTIFICATIONS_PATH = "/api/v1/me/notifications";
export const PANEL_LIMIT = 50;
export const BADGE_REFRESH_MS = 60_000;

export type NotificationTab = "unread" | "all";

const EVERY_NOTIFICATION = queryKey("notifications", "tenant");

export function unreadBadgeKey(): QueryKey {
  return queryKey("notifications", "tenant", { badge: true });
}

export function notificationListKey(tab: NotificationTab): QueryKey {
  return queryKey("notifications", "tenant", { tab });
}

export interface UnreadBadge {
  readonly count: number;
  /** True for the `100000+` cap of `X-Erev-Total-Count`. */
  readonly capped: boolean;
  /** The newest unread notification, for the DS-CMP-05 announcement of a new approval request. */
  readonly newest: Notification | null;
}

export async function fetchUnreadBadge(): Promise<UnreadBadge> {
  const page = await fetchListPage<Notification>(NOTIFICATIONS_PATH, { unread: true }, null, {
    limit: 1,
    count: true,
  });
  return {
    count: page.total?.count ?? page.items.length,
    capped: page.total?.capped ?? false,
    newest: page.items[0] ?? null,
  };
}

export function useUnreadBadge() {
  const queryClient = useQueryClient();
  useEffect(
    () =>
      onCommandSucceeded(() => {
        // A refetch already in flight (for example after a notification command) is kept.
        void queryClient.invalidateQueries(
          { queryKey: unreadBadgeKey() },
          { cancelRefetch: false },
        );
      }),
    [queryClient],
  );
  return useQuery({
    queryKey: unreadBadgeKey(),
    queryFn: fetchUnreadBadge,
    refetchInterval: BADGE_REFRESH_MS,
    refetchIntervalInBackground: false,
    refetchOnWindowFocus: true,
  });
}

export async function fetchNotifications(tab: NotificationTab): Promise<readonly Notification[]> {
  const page = await fetchListPage<Notification>(
    NOTIFICATIONS_PATH,
    tab === "unread" ? { unread: true } : {},
    null,
    { limit: PANEL_LIMIT, count: false },
  );
  return page.items;
}

/** A panel tab; each opening of the panel reads the list again. */
export function useNotifications(tab: NotificationTab, enabled = true) {
  return useQuery({
    queryKey: notificationListKey(tab),
    queryFn: () => fetchNotifications(tab),
    staleTime: 0,
    enabled,
  });
}

export function useMarkAllRead() {
  return useCommand<ReadAllOut>({
    method: "POST",
    path: `${NOTIFICATIONS_PATH}/read-all`,
    invalidates: [EVERY_NOTIFICATION],
  });
}

export function useMarkRead(notificationId: string) {
  return useCommand<Notification>({
    method: "POST",
    path: `${NOTIFICATIONS_PATH}/${notificationId}/read`,
    invalidates: [EVERY_NOTIFICATION],
  });
}
