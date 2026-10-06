// SF-15:notifications Notification preferences (SCREENS_B §9.8; SCREENS §0.3 SCR-IA-03, §0.4 RT-72;
// DESIGN_SYSTEM DS-CMP-07, DS-CMP-10 static table, DS-CMP-21 switch, DS-CMP-22, DS-CMP-27; PRD §5.4
// NTF-01 to NTF-12, NTF-R2, NTF-R3; 04 API-R-03 `GET, PUT /me/notification-preferences`, T-PLT-25, E-69;
// 03 REQ-PLT-021). The table "Notification preferences" lists the twelve kinds in PRD order, each with
// an "In app" and an "Email" switch. A switch applies at once: it turns and shows its busy state while
// `PUT /me/notification-preferences` sends the full list. Success shows "Preferences saved." at most
// once per 5 seconds; failure returns every switch to the last stored list with "Could not save the
// preference. Try again.". The `CHAIN_VERIFICATION_FAILED` switches stay on with `aria-disabled` and the
// NTF-R2 tooltip, and every body sends that kind on in both channels. A sandbox sends no email (05
// SBX-08 rev 1.116; SCREENS_B §9.8 rev 1.54): there every "Email" switch is off and unavailable with its
// reason, the footnote says so, and the stored email preferences are sent as they are.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { sandboxTenantName, useShellSession } from "../../app/shell/SandboxIndicator";
import { Banner } from "../../components/feedback/Banner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { Info } from "../../components/icons/registry";
import { Button } from "../../components/ui/Button";
import { cn } from "../../components/ui/cn";
import { Tooltip, type TooltipTriggerProps } from "../../components/ui/Tooltip";
import { api, unwrap } from "../../lib/api/client";
import { useCommand } from "../../lib/api/commands";
import { queryKey, type QueryKey } from "../../lib/api/query-keys";
import type { components } from "../../lib/api/schema";
import { t } from "../../lib/i18n/t";
import { testIdKey } from "../onboarding/select-workspace";
import { SettingsPageHeader } from "./index";

export type NotificationKind = components["schemas"]["NotificationKind"];
export type NotificationPreference = components["schemas"]["NotificationPreferenceOut"];
type NotificationPreferences = components["schemas"]["NotificationPreferencesOut"];

export const NOTIFICATION_PREFERENCES_PATH = "/api/v1/me/notification-preferences";
/** SCREENS_B §9.8: "Preferences saved." at most once per 5 seconds. */
export const SAVED_TOAST_INTERVAL_MS = 5_000;
/** PRD NTF-R2 (04 `ck_notification_preference__mandatory`): NTF-09 cannot be turned off. */
export const MANDATORY_KIND: NotificationKind = "CHAIN_VERIFICATION_FAILED";

/** SCREENS_B §9.8 row order (PRD §5.4 NTF-01 to NTF-12). */
export const PREFERENCE_KINDS: readonly NotificationKind[] = [
  "APPROVAL_ASSIGNED",
  "ITEM_APPROVED",
  "ITEM_REJECTED",
  "APPROVAL_VOIDED",
  "JOB_FAILED",
  "PERIOD_LOCKED",
  "PERIOD_REOPENED",
  "CLOSE_BLOCKER_RAISED",
  "CHAIN_VERIFICATION_FAILED",
  "EXPORT_FAILED",
  "EXCEPTION_ASSIGNED",
  "SUPPORT_GRANT_REQUESTED",
];

export type Channel = "in_app" | "email";

export function preferencesKey(): QueryKey {
  return queryKey("notification-preferences", "tenant");
}

export function fetchNotificationPreferences(): Promise<NotificationPreferences> {
  return unwrap(api.GET("/api/v1/me/notification-preferences"));
}

/** The list with one switch set. */
export function withChange(
  items: readonly NotificationPreference[],
  kind: NotificationKind,
  channel: Channel,
  value: boolean,
): readonly NotificationPreference[] {
  return items.map((item) => {
    if (item.kind !== kind) {
      return item;
    }
    return channel === "in_app" ? { ...item, in_app: value } : { ...item, email: value };
  });
}

/** The PUT body: every kind of the list, with the audit chain kind on in both channels (NTF-R2). */
export function preferencesBody(items: readonly NotificationPreference[]): {
  readonly items: readonly NotificationPreference[];
} {
  return {
    items: items.map((item) =>
      item.kind === MANDATORY_KIND
        ? { kind: item.kind, in_app: true, email: true }
        : { kind: item.kind, in_app: item.in_app, email: item.email },
    ),
  };
}

function switchId(kind: NotificationKind, channel: Channel): string {
  return `${kind}:${channel}`;
}

export function NotificationPreferences() {
  const title = t("settings.notifications.title");
  const sandbox = sandboxTenantName(useShellSession()) !== null;
  const preferences = useQuery({
    queryKey: preferencesKey(),
    queryFn: fetchNotificationPreferences,
  });

  let body;
  if (preferences.data !== undefined) {
    body = <PreferencesTable stored={preferences.data.items} sandbox={sandbox} />;
  } else if (preferences.isError) {
    body = (
      <Banner
        tone="negative"
        title={t("settings.notifications.loadError")}
        actions={
          <Button variant="link" onClick={() => void preferences.refetch()}>
            {t("settings.notifications.retry")}
          </Button>
        }
      >
        {preferences.error.message}
      </Banner>
    );
  } else {
    body = <Skeleton region={title} shape="rows" count={12} />;
  }

  return (
    <div className="flex w-full max-w-[var(--content-max-form)] flex-col gap-6 px-[var(--gutter)] py-6">
      <SettingsPageHeader title={title} group="preferences" />
      {body}
    </div>
  );
}

interface PreferencesTableProps {
  readonly stored: readonly NotificationPreference[];
  /** The workspace is a sandbox: notifications are delivered in the app only (05 SBX-08). */
  readonly sandbox: boolean;
}

function PreferencesTable({ stored, sandbox }: PreferencesTableProps) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const save = useCommand<NotificationPreferences>({
    method: "PUT",
    path: NOTIFICATION_PREFERENCES_PATH,
  });
  const [items, setItems] = useState<readonly NotificationPreference[]>(stored);
  const [busy, setBusy] = useState<ReadonlySet<string>>(() => new Set());
  const shown = useRef(stored);
  const confirmed = useRef(stored);
  const sequence = useRef(0);
  const savedToastAt = useRef<number | null>(null);

  const show = (next: readonly NotificationPreference[]) => {
    shown.current = next;
    setItems(next);
  };
  const markBusy = (id: string, on: boolean) => {
    setBusy((current) => {
      const next = new Set(current);
      if (on) {
        next.add(id);
      } else {
        next.delete(id);
      }
      return next;
    });
  };

  const toggle = async (kind: NotificationKind, channel: Channel, value: boolean) => {
    const id = switchId(kind, channel);
    const next = withChange(shown.current, kind, channel, value);
    sequence.current += 1;
    const request = sequence.current;
    show(next);
    markBusy(id, true);
    const outcome = await save.submit(preferencesBody(next));
    markBusy(id, false);
    if (outcome.kind === "succeeded") {
      const answered = outcome.data?.items ?? next;
      confirmed.current = answered;
      queryClient.setQueryData<NotificationPreferences>(preferencesKey(), { items: [...answered] });
      // A later change is already on screen and on its way; only the latest answer replaces the list.
      if (request === sequence.current) {
        show(answered);
      }
      const now = Date.now();
      if (savedToastAt.current === null || now - savedToastAt.current >= SAVED_TOAST_INTERVAL_MS) {
        savedToastAt.current = now;
        toast.show({ tone: "positive", message: t("settings.notifications.saved") });
      }
      return;
    }
    show(confirmed.current);
    toast.show({ tone: "negative", message: t("settings.notifications.saveFailed") });
  };

  const byKind = new Map(items.map((item) => [item.kind, item]));
  const header = "px-3 py-2 text-start font-medium text-fg-2";
  const cell = "px-3 py-3 align-top";

  return (
    <div className="flex flex-col gap-3">
      <table
        aria-label={t("settings.notifications.table")}
        data-testid="SF-15-grid-notification-preferences"
        className="w-full border-collapse text-body-sm"
      >
        <thead>
          <tr className="border-b border-default bg-subtle">
            <th scope="col" className={header}>
              {t("settings.notifications.column.notification")}
            </th>
            <th scope="col" className={header}>
              {t("settings.notifications.column.sent")}
            </th>
            <th scope="col" className={cn(header, "w-20")}>
              {t("settings.notifications.column.inApp")}
            </th>
            <th scope="col" className={cn(header, "w-24")}>
              {t("settings.notifications.column.email")}
            </th>
          </tr>
        </thead>
        <tbody>
          {PREFERENCE_KINDS.map((kind) => {
            const item = byKind.get(kind);
            if (item === undefined) {
              return null;
            }
            const name = t(`settings.notifications.kinds.${kind}.name`);
            const mandatory = kind === MANDATORY_KIND;
            const inAppOnly = mandatory && sandbox;
            const reason = mandatory
              ? t(
                  inAppOnly
                    ? "settings.notifications.sandbox.mandatory"
                    : "settings.notifications.mandatory",
                )
              : undefined;
            return (
              <tr
                key={kind}
                data-testid={`SF-15-row-${testIdKey(kind)}`}
                className="border-b border-hairline"
              >
                <th scope="row" className={cn(cell, "text-start font-medium text-fg-1")}>
                  {name}
                </th>
                <td className={cn(cell, "text-fg-2")}>
                  {t(`settings.notifications.kinds.${kind}.description`)}
                </td>
                <td className={cell}>
                  <PreferenceSwitch
                    label={t("settings.notifications.switch.inApp", { notification: name })}
                    checked={mandatory || item.in_app}
                    busy={busy.has(switchId(kind, "in_app"))}
                    disabledReason={reason}
                    onToggle={() => void toggle(kind, "in_app", !item.in_app)}
                  />
                </td>
                <td className={cell}>
                  <span className="inline-flex items-center gap-2">
                    <PreferenceSwitch
                      label={t("settings.notifications.switch.email", { notification: name })}
                      checked={!sandbox && (mandatory || item.email)}
                      busy={busy.has(switchId(kind, "email"))}
                      disabledReason={sandbox ? t("settings.notifications.sandbox.email") : reason}
                      onToggle={() => void toggle(kind, "email", !item.email)}
                    />
                    {mandatory ? <Info aria-hidden="true" className="shrink-0 text-fg-3" /> : null}
                  </span>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <p className="text-body-sm text-fg-3">
        {t(sandbox ? "settings.notifications.sandbox.footnote" : "settings.notifications.footnote")}
      </p>
    </div>
  );
}

interface PreferenceSwitchProps {
  readonly label: string;
  readonly checked: boolean;
  readonly busy: boolean;
  readonly disabledReason: string | undefined;
  readonly onToggle: () => void;
}

/**
 * A DS-CMP-21 switch named "<notification>, <channel>"; the column header is its visible label. While its
 * change is saved it is busy and ignores presses. An unavailable switch keeps focus through
 * aria-disabled and states its reason in a tooltip (DS-CMP-27).
 */
function PreferenceSwitch({
  label,
  checked,
  busy,
  disabledReason,
  onToggle,
}: PreferenceSwitchProps) {
  const unavailable = disabledReason !== undefined;
  const render = (trigger: TooltipTriggerProps | null) => (
    <button
      type="button"
      role="switch"
      aria-label={label}
      aria-checked={checked}
      aria-disabled={unavailable ? true : undefined}
      aria-busy={busy ? true : undefined}
      aria-describedby={trigger?.["aria-describedby"]}
      onClick={() => {
        if (!unavailable && !busy) {
          onToggle();
        }
      }}
      onMouseEnter={trigger?.onMouseEnter}
      onMouseLeave={trigger?.onMouseLeave}
      onFocus={trigger?.onFocus}
      onBlur={trigger?.onBlur}
      onKeyDown={trigger?.onKeyDown}
      className={cn(
        "inline-flex h-6 w-10 shrink-0 items-center rounded-full border p-0.5",
        checked
          ? "justify-end border-accent-solid bg-accent-solid"
          : "justify-start border-control bg-subtle",
        unavailable ? "cursor-not-allowed" : busy ? "cursor-progress" : "cursor-pointer",
      )}
    >
      <span className={cn("size-4 rounded-full", checked ? "bg-on-accent" : "bg-fg-3")} />
    </button>
  );
  return unavailable ? <Tooltip content={disabledReason}>{render}</Tooltip> : render(null);
}
