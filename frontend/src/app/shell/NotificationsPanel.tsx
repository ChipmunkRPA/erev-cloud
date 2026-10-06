// Notifications bell and panel (DESIGN_SYSTEM DS-CMP-05; SCREENS §1.2 SF-21; 04 API-R-03, T-PLT-24, E-69).
// The bell is named "Notifications, <n> unread" and shows the unread badge (up to 99, then "99+"). The
// badge query refetches every 60 seconds while the page is visible, on window focus and after every
// successful command. The non-modal panel has the header "Notifications" with "Mark all as read" (while
// the Unread tab lists an item) and the "Notification preferences" link (when SF-15:notifications is
// built), the tabs "Unread" and "All", and one link per notification: selecting it opens `link_path` and
// sends `POST /me/notifications/{id}/read`. "Mark all as read" sends `before` = the newest `created_at`
// loaded and announces "Marked <marked> notifications as read". Only a new APPROVAL_ASSIGNED
// notification is announced, once. Enter or Space opens the panel and focuses the first item; Esc
// closes it and returns focus to the bell.
import { useEffect, useId, useRef, useState } from "react";
import { Link } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { Skeleton } from "../../components/feedback/Skeleton";
import {
  Bell,
  CheckCircle,
  type Icon,
  Info,
  LockSimple,
  LockSimpleOpen,
  Prohibit,
  SealCheck,
  WarningCircle,
  XCircle,
} from "../../components/icons/registry";
import { PanelTabs } from "../../components/record/Tabs";
import { Button } from "../../components/ui/Button";
import { cn } from "../../components/ui/cn";
import { Tooltip } from "../../components/ui/Tooltip";
import { announce } from "../../lib/a11y/announce";
import {
  type Notification,
  type NotificationKind,
  type NotificationTab,
  useMarkAllRead,
  useMarkRead,
  useNotifications,
  useUnreadBadge,
} from "../../lib/api/queries/notifications";
import { formatNumber, formatRelative, formatTimestamp, instantMs } from "../../lib/format";
import { t } from "../../lib/i18n/t";

/** DS-CMP-05 kind icons; the title carries the meaning (DS-ICO-06). */
export const KIND_ICON: Readonly<
  Record<NotificationKind, { readonly icon: Icon; readonly tone: string }>
> = {
  APPROVAL_ASSIGNED: { icon: SealCheck, tone: "text-fg-2" },
  ITEM_APPROVED: { icon: CheckCircle, tone: "text-positive-fg" },
  ITEM_REJECTED: { icon: XCircle, tone: "text-negative-fg" },
  APPROVAL_VOIDED: { icon: Prohibit, tone: "text-fg-2" },
  JOB_FAILED: { icon: XCircle, tone: "text-negative-fg" },
  PERIOD_LOCKED: { icon: LockSimple, tone: "text-fg-2" },
  PERIOD_REOPENED: { icon: LockSimpleOpen, tone: "text-warning-fg" },
  CLOSE_BLOCKER_RAISED: { icon: WarningCircle, tone: "text-warning-fg" },
  CHAIN_VERIFICATION_FAILED: { icon: XCircle, tone: "text-negative-fg" },
  EXPORT_FAILED: { icon: XCircle, tone: "text-negative-fg" },
  EXCEPTION_ASSIGNED: { icon: WarningCircle, tone: "text-warning-fg" },
  SUPPORT_GRANT_REQUESTED: { icon: Info, tone: "text-info-fg" },
};

export const BADGE_MAX = 99;
/** SCREENS RT-72 SF-15:notifications. */
export const PREFERENCES_ROUTE = "/settings/notifications";

/** A capped figure: the count and a plus sign, as `X-Erev-Total-Count` writes `100000+`. */
function cappedFigure(count: number): string {
  return `${formatNumber(count)}+`;
}

/** DS-CMP-05 badge: the count up to 99, then `99+`. */
export function badgeText(count: number, capped: boolean): string {
  return capped || count > BADGE_MAX ? cappedFigure(BADGE_MAX) : formatNumber(count);
}

/** The newest `created_at` among loaded notifications, as the API wrote it. */
export function newestCreatedAt(items: readonly Notification[]): string | null {
  let newest: string | null = null;
  for (const item of items) {
    if (newest === null || instantMs(item.created_at) > instantMs(newest)) {
      newest = item.created_at;
    }
  }
  return newest;
}

export interface NotificationsPanelProps {
  /** The built route paths; the preferences link renders only when its route is built. */
  readonly built: ReadonlySet<string>;
}

export function NotificationsPanel({ built }: NotificationsPanelProps) {
  const badge = useUnreadBadge();
  const panelId = useId();
  const root = useRef<HTMLSpanElement>(null);
  const bell = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [focusFirst, setFocusFirst] = useState(false);

  const count = badge.data?.count ?? 0;
  const capped = badge.data?.capped ?? false;
  const unread = count > 0 || capped;
  const name = unread
    ? t("shell.notifications.buttonUnread", {
        shown: capped ? cappedFigure(count) : formatNumber(count),
      })
    : t("shell.notifications.button");

  // DS-CMP-05: a new APPROVAL_ASSIGNED notification for the current user is announced once.
  const seen = useRef<string | null | undefined>(undefined);
  const newest = badge.data?.newest ?? null;
  useEffect(() => {
    if (badge.data === undefined) {
      return;
    }
    const id = newest?.id ?? null;
    if (
      seen.current !== undefined &&
      newest !== null &&
      id !== seen.current &&
      newest.kind === "APPROVAL_ASSIGNED"
    ) {
      announce(newest.title, "polite");
    }
    seen.current = id;
  }, [badge.data, newest]);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const onPointerDown = (event: PointerEvent) => {
      if (event.target instanceof Node && root.current?.contains(event.target) !== true) {
        setOpen(false);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => {
      document.removeEventListener("pointerdown", onPointerDown);
    };
  }, [open]);

  const close = (returnFocus: boolean) => {
    setOpen(false);
    if (returnFocus) {
      bell.current?.focus();
    }
  };

  return (
    <span ref={root} className="relative inline-flex">
      <button
        ref={bell}
        type="button"
        aria-label={name}
        aria-haspopup="dialog"
        aria-expanded={open}
        aria-controls={open ? panelId : undefined}
        onClick={() => {
          setFocusFirst(false);
          setOpen((current) => !current);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            setFocusFirst(true);
            setOpen(true);
          }
        }}
        className="relative flex size-[var(--control-h)] items-center justify-center rounded-md text-fg-2 hover:bg-hover hover:text-fg-1"
      >
        <Bell aria-hidden="true" size={20} />
        {unread ? (
          <span
            aria-hidden="true"
            className="absolute end-0 top-0 min-w-4 rounded-full bg-inverse px-1 text-caption tabular-nums text-fg-inverse"
          >
            {badgeText(count, capped)}
          </span>
        ) : null}
      </button>
      {open ? (
        <NotificationsDialog id={panelId} built={built} focusFirst={focusFirst} onClose={close} />
      ) : null}
    </span>
  );
}

interface NotificationsDialogProps {
  readonly id: string;
  readonly built: ReadonlySet<string>;
  readonly focusFirst: boolean;
  readonly onClose: (returnFocus: boolean) => void;
}

function NotificationsDialog({ id, built, focusFirst, onClose }: NotificationsDialogProps) {
  const panel = useRef<HTMLDivElement>(null);
  const latestClose = useRef(onClose);
  useEffect(() => {
    latestClose.current = onClose;
  });
  useEffect(() => {
    const root = panel.current;
    if (root === null) {
      return undefined;
    }
    const onKeyDown = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        latestClose.current(true);
      }
    };
    root.addEventListener("keydown", onKeyDown);
    return () => {
      root.removeEventListener("keydown", onKeyDown);
    };
  }, []);
  const [tab, setTab] = useState<NotificationTab>("unread");
  const unreadList = useNotifications("unread");
  const allList = useNotifications("all", tab === "all");
  const markAll = useMarkAllRead();
  const current = tab === "unread" ? unreadList : allList;
  const unreadItems = unreadList.data ?? [];

  const onMarkAll = async () => {
    const before = newestCreatedAt([...unreadItems, ...(allList.data ?? [])]);
    if (before === null) {
      return;
    }
    const outcome = await markAll.submit({ before });
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      announce(t("shell.notifications.marked", { count: outcome.data.marked }), "polite");
    }
  };

  return (
    <div
      ref={panel}
      id={id}
      role="dialog"
      aria-label={t("shell.notifications.title")}
      className="absolute end-0 top-full z-[var(--z-popover)] mt-1 flex w-100 max-w-[var(--modal-w-sm)] flex-col overflow-hidden rounded-lg border border-hairline bg-raised shadow-popover"
      style={{ maxBlockSize: "70vh" }}
    >
      <div className="flex items-center justify-between gap-3 px-4 pb-2 pt-3">
        <h2 className="text-title-sm text-fg-1">{t("shell.notifications.title")}</h2>
        <div className="flex items-center gap-3">
          {unreadItems.length > 0 ? (
            <Button
              variant="link"
              loading={markAll.pending}
              onClick={() => {
                void onMarkAll();
              }}
            >
              {t("shell.notifications.markAll")}
            </Button>
          ) : null}
          {built.has(PREFERENCES_ROUTE) ? (
            <Link
              to={PREFERENCES_ROUTE}
              onClick={() => {
                onClose(false);
              }}
              className="text-body-sm text-accent-fg hover:underline"
            >
              {t("shell.notifications.preferences")}
            </Link>
          ) : null}
        </div>
      </div>
      <div className="flex min-h-0 flex-col px-4">
        <PanelTabs
          label={t("shell.notifications.tabs")}
          tabs={[
            { id: "unread", label: t("shell.notifications.tab.unread") },
            { id: "all", label: t("shell.notifications.tab.all") },
          ]}
          selectedId={tab}
          onChange={(next) => {
            setTab(next === "all" ? "all" : "unread");
          }}
        >
          <NotificationList
            query={current}
            focusFirst={focusFirst}
            onNavigate={() => {
              onClose(false);
            }}
          />
        </PanelTabs>
      </div>
    </div>
  );
}

interface NotificationListProps {
  readonly query: ReturnType<typeof useNotifications>;
  readonly focusFirst: boolean;
  readonly onNavigate: () => void;
}

function NotificationList({ query, focusFirst, onNavigate }: NotificationListProps) {
  if (query.isPending) {
    return (
      <div className="py-3">
        <Skeleton region={t("shell.notifications.region")} shape="rows" count={4} />
      </div>
    );
  }
  if (query.isError) {
    return (
      <div className="py-3">
        <Banner
          tone="negative"
          headingLevel={3}
          title={t("shell.notifications.loadError")}
          actions={
            <Button
              variant="link"
              onClick={() => {
                void query.refetch();
              }}
            >
              {t("shell.notifications.retry")}
            </Button>
          }
        />
      </div>
    );
  }
  const items = query.data;
  if (items.length === 0) {
    return <p className="py-6 text-body-sm text-fg-2">{t("shell.notifications.empty")}</p>;
  }
  return (
    <ul className="-mx-3 flex flex-col overflow-y-auto py-1">
      {items.map((notification, index) => (
        <NotificationItem
          key={notification.id}
          notification={notification}
          focusOnMount={focusFirst && index === 0}
          onNavigate={onNavigate}
        />
      ))}
    </ul>
  );
}

interface NotificationItemProps {
  readonly notification: Notification;
  readonly focusOnMount: boolean;
  readonly onNavigate: () => void;
}

function NotificationItem({ notification, focusOnMount, onNavigate }: NotificationItemProps) {
  const markRead = useMarkRead(notification.id);
  const link = useRef<HTMLAnchorElement>(null);
  useEffect(() => {
    if (focusOnMount) {
      link.current?.focus();
    }
  }, [focusOnMount]);
  const { icon: KindIcon, tone } = KIND_ICON[notification.kind];
  const unread = notification.read_at === null;
  const absolute = formatTimestamp(notification.created_at);

  return (
    <li className="relative flex gap-2.5 rounded-md px-3 py-2 hover:bg-hover">
      <KindIcon aria-hidden="true" className={cn("mt-0.5 shrink-0", tone)} />
      <div className="flex min-w-0 flex-1 flex-col gap-0.5">
        {notification.link_path === null ? (
          <span className="text-body-sm font-medium text-fg-1">{notification.title}</span>
        ) : (
          <Link
            ref={link}
            to={notification.link_path}
            onClick={() => {
              if (unread) {
                void markRead.submit();
              }
              onNavigate();
            }}
            className="text-body-sm font-medium text-fg-1 hover:underline"
          >
            {notification.title}
          </Link>
        )}
        {notification.body === null ? null : (
          <p className="truncate text-body-sm text-fg-2">{notification.body}</p>
        )}
        <Tooltip content={absolute}>
          {(trigger) => (
            <time
              dateTime={notification.created_at}
              aria-describedby={trigger["aria-describedby"]}
              onMouseEnter={trigger.onMouseEnter}
              onMouseLeave={trigger.onMouseLeave}
              onFocus={trigger.onFocus}
              onBlur={trigger.onBlur}
              className="text-caption text-fg-3"
            >
              {formatRelative(notification.created_at, Date.now())}
            </time>
          )}
        </Tooltip>
      </div>
      {unread ? (
        <>
          <span
            aria-hidden="true"
            className="mt-1.5 size-2 shrink-0 rounded-full bg-accent-solid"
          />
          <span className="sr-only">{t("shell.notifications.unread")}</span>
        </>
      ) : null}
    </li>
  );
}
