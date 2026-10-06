// User menu (DESIGN_SYSTEM DS-CMP-01 item 9, DS-DEN-01; SCREENS §1.3 SF-23; 04 §16.12). The avatar button
// (initials, 28 px) opens an APG menu under the user's name and email: "Switch tenant" when `GET /me`
// lists more than one membership (SF-23), Theme (System, Light, Dark) and Density (Comfortable, Compact)
// as radio items, then "Sign out". A theme or density choice applies at once, is mirrored to
// `erev.theme` or `erev.density` (DG-FE-13) and is stored through `PATCH /me/preferences`; the
// preferences that `GET /me` returns are applied when they change, so the choice follows the user.
import { useQueryClient } from "@tanstack/react-query";
import { type KeyboardEvent, useCallback, useEffect, useId, useRef, useState } from "react";
import { useNavigate } from "react-router";

import { Circle, type Icon, SignOut } from "../../components/icons/registry";
import { cn } from "../../components/ui/cn";
import { SIGN_IN_PATH } from "../../lib/api/client";
import { useCommand } from "../../lib/api/commands";
import { type Preferences, useMe, useUpdatePreferences } from "../../lib/api/queries/me";
import type { components } from "../../lib/api/schema";
import { configureFormat } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { type Density, type ThemePreference, useI18n, useTheme } from "../providers";
import { openTenantId } from "./open-workspace";
import { useShellSession } from "./SandboxIndicator";
import { switchableMemberships, TenantSwitcher } from "./TenantSwitcher";

type UiTheme = components["schemas"]["UiTheme"];
type UiDensity = components["schemas"]["UiDensity"];

export const LOGOUT_PATH = "/api/v1/session/logout";
export const THEMES: readonly ThemePreference[] = ["system", "light", "dark"];
export const DENSITIES: readonly Density[] = ["comfortable", "compact"];

const THEME_API: Readonly<Record<ThemePreference, UiTheme>> = {
  system: "SYSTEM",
  light: "LIGHT",
  dark: "DARK",
};
const DENSITY_API: Readonly<Record<Density, UiDensity>> = {
  comfortable: "COMFORTABLE",
  compact: "COMPACT",
};
const THEME_OF: Readonly<Record<UiTheme, ThemePreference>> = {
  SYSTEM: "system",
  LIGHT: "light",
  DARK: "dark",
};
const DENSITY_OF: Readonly<Record<UiDensity, Density>> = {
  COMFORTABLE: "comfortable",
  COMPACT: "compact",
};

export interface DisplayPreferences {
  readonly theme: ThemePreference;
  readonly density: Density;
  readonly chooseTheme: (theme: ThemePreference) => void;
  readonly chooseDensity: (density: Density) => void;
}

/** DS-DEN-01: a choice applies and is mirrored at once, then is stored server-side. */
export function useDisplayPreferences(): DisplayPreferences {
  const { theme, density, setTheme, setDensity } = useTheme();
  const { update } = useUpdatePreferences();
  const chooseTheme = useCallback(
    (next: ThemePreference) => {
      setTheme(next);
      void update({ theme: THEME_API[next] });
    },
    [setTheme, update],
  );
  const chooseDensity = useCallback(
    (next: Density) => {
      setDensity(next);
      void update({ density: DENSITY_API[next] });
    },
    [setDensity, update],
  );
  return { theme, density, chooseTheme, chooseDensity };
}

/**
 * Applies the theme, density and number format of `GET /me` whenever the server values change; the
 * format locale reaches `src/lib/format` and the I18n context (DS-I18N-02, REQ-UX-022; WEB-12).
 */
export function useServerPreferences(preferences: Preferences | undefined): void {
  const themeValue = useTheme();
  const { setProfileLocale } = useI18n();
  const latest = useRef(themeValue);
  useEffect(() => {
    latest.current = themeValue;
  });
  const serverTheme = preferences?.theme;
  const serverDensity = preferences?.density;
  const serverLocale = preferences?.format_locale;
  useEffect(() => {
    if (serverLocale !== undefined) {
      configureFormat({ locale: serverLocale });
      setProfileLocale(serverLocale);
    }
  }, [serverLocale, setProfileLocale]);
  useEffect(() => {
    if (serverTheme !== undefined && latest.current.theme !== THEME_OF[serverTheme]) {
      latest.current.setTheme(THEME_OF[serverTheme]);
    }
  }, [serverTheme]);
  useEffect(() => {
    if (serverDensity !== undefined && latest.current.density !== DENSITY_OF[serverDensity]) {
      latest.current.setDensity(DENSITY_OF[serverDensity]);
    }
  }, [serverDensity]);
}

/** `POST /session/logout`, then the cache is cleared and sign-in opens. */
export function useSignOut(): () => Promise<void> {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { submit } = useCommand({ method: "POST", path: LOGOUT_PATH });
  return useCallback(async () => {
    const outcome = await submit();
    if (outcome.kind === "succeeded") {
      queryClient.clear();
      void navigate(SIGN_IN_PATH, { replace: true });
    }
  }, [navigate, queryClient, submit]);
}

/** The first letters of the first and last words of a display name. */
export function initials(name: string): string {
  const words = name
    .trim()
    .split(/\s+/)
    .filter((word) => word !== "");
  const first = words[0]?.charAt(0) ?? "";
  const last = words.length > 1 ? (words.at(-1)?.charAt(0) ?? "") : "";
  return `${first}${last}`.toLocaleUpperCase();
}

interface MenuEntry {
  readonly id: string;
  readonly label: string;
  readonly role: "menuitem" | "menuitemradio";
  readonly checked?: boolean;
  readonly icon?: Icon;
  readonly onSelect: () => void;
}

interface MenuSection {
  readonly id: string;
  readonly label: string | null;
  readonly entries: readonly MenuEntry[];
}

export interface UserMenuProps {
  /** The built route paths ("All workspaces" links SF-23:select only when it is built). */
  readonly built: ReadonlySet<string>;
  /** The landing route a tenant switch opens (BS-D-08). */
  readonly homePath: string;
}

export function UserMenu({ built, homePath }: UserMenuProps) {
  const me = useMe();
  const session = useShellSession();
  useServerPreferences(me.data?.preferences);
  const { theme, density, chooseTheme, chooseDensity } = useDisplayPreferences();
  const signOut = useSignOut();
  const menuId = useId();
  const triggerId = useId();
  const [open, setOpen] = useState(false);
  const [switching, setSwitching] = useState(false);
  const [active, setActive] = useState(0);
  const root = useRef<HTMLSpanElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const itemRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const user = me.data?.user ?? (session?.authenticated === true ? session.user : null);
  const name = user?.display_name ?? "";
  const memberships = me.data?.memberships ?? [];
  // SCREENS §1.3: "Switch tenant" with more than one workspace to open; an archived sandbox still
  // lists in GET /me (04 §16.12 rev 1.125) and is none (05 SBX-07).
  const openId = openTenantId(session);
  const switchable = switchableMemberships(memberships, openId);

  const sections: MenuSection[] = [];
  if (switchable.length > 1) {
    sections.push({
      id: "tenant",
      label: null,
      entries: [
        {
          id: "switch-tenant",
          role: "menuitem",
          label: t("shell.userMenu.switchTenant"),
          onSelect: () => {
            setSwitching(true);
          },
        },
      ],
    });
  }
  sections.push(
    {
      id: "theme",
      label: t("shell.userMenu.theme"),
      entries: THEMES.map((value) => ({
        id: `theme-${value}`,
        role: "menuitemradio",
        checked: theme === value,
        label: t(`shell.userMenu.themes.${value}`),
        onSelect: () => {
          chooseTheme(value);
        },
      })),
    },
    {
      id: "density",
      label: t("shell.userMenu.density"),
      entries: DENSITIES.map((value) => ({
        id: `density-${value}`,
        role: "menuitemradio",
        checked: density === value,
        label: t(`shell.userMenu.densities.${value}`),
        onSelect: () => {
          chooseDensity(value);
        },
      })),
    },
    {
      id: "session",
      label: null,
      entries: [
        {
          id: "sign-out",
          role: "menuitem",
          icon: SignOut,
          label: t("shell.userMenu.signOut"),
          onSelect: () => {
            void signOut();
          },
        },
      ],
    },
  );
  const entries = sections.flatMap((section) => section.entries);

  useEffect(() => {
    if (open) {
      itemRefs.current[active]?.focus();
    }
  }, [open, active]);

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

  const openAt = (index: number) => {
    setActive(index);
    setOpen(true);
  };
  const close = (returnFocus: boolean) => {
    setOpen(false);
    if (returnFocus) {
      trigger.current?.focus();
    }
  };

  const onTriggerKeyDown = (event: KeyboardEvent<HTMLButtonElement>) => {
    if (event.key === "Enter" || event.key === " " || event.key === "ArrowDown") {
      event.preventDefault();
      openAt(0);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      openAt(entries.length - 1);
    }
  };

  const onMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const count = entries.length;
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setActive((index) => (index + 1) % count);
        return;
      case "ArrowUp":
        event.preventDefault();
        setActive((index) => (index - 1 + count) % count);
        return;
      case "Home":
        event.preventDefault();
        setActive(0);
        return;
      case "End":
        event.preventDefault();
        setActive(count - 1);
        return;
      case "Escape":
        event.preventDefault();
        event.stopPropagation();
        close(true);
        return;
      case "Tab":
        close(false);
        return;
      default:
        if (event.key.length === 1 && !event.altKey && !event.ctrlKey && !event.metaKey) {
          const key = event.key.toLocaleLowerCase();
          for (let step = 1; step <= count; step += 1) {
            const index = (active + step) % count;
            if (entries[index]?.label.toLocaleLowerCase().startsWith(key) === true) {
              setActive(index);
              break;
            }
          }
        }
    }
  };

  return (
    <span ref={root} className="relative inline-flex">
      <button
        ref={trigger}
        id={triggerId}
        type="button"
        aria-label={t("shell.userMenu.label", { name })}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => {
          if (open) {
            close(false);
          } else {
            openAt(0);
          }
        }}
        onKeyDown={onTriggerKeyDown}
        className="flex size-7 items-center justify-center rounded-full bg-neutral-chip-bg text-caption font-semibold text-fg-1 hover:bg-active"
      >
        <span aria-hidden="true">{initials(name)}</span>
      </button>
      {open ? (
        <div className="absolute end-0 top-full z-[var(--z-popover)] mt-1 flex min-w-56 flex-col rounded-lg border border-hairline bg-raised p-1 shadow-popover">
          <div className="flex flex-col px-2 pb-2 pt-1">
            <span className="text-body-sm font-medium text-fg-1">{name}</span>
            {user === null ? null : <span className="text-caption text-fg-3">{user.email}</span>}
          </div>
          <div
            id={menuId}
            role="menu"
            tabIndex={-1}
            aria-labelledby={triggerId}
            onKeyDown={onMenuKeyDown}
            className="flex flex-col"
          >
            {sections.map((section) => (
              <div
                key={section.id}
                role="group"
                aria-label={section.label ?? undefined}
                className="flex flex-col border-t border-hairline py-1"
              >
                {section.label === null ? null : (
                  <div aria-hidden="true" className="px-2 pb-1 pt-1.5 text-caption text-fg-3">
                    {section.label}
                  </div>
                )}
                {section.entries.map((entry) => {
                  const position = entries.indexOf(entry);
                  const EntryIcon = entry.icon;
                  return (
                    <button
                      key={entry.id}
                      ref={(element) => {
                        itemRefs.current[position] = element;
                      }}
                      type="button"
                      role={entry.role}
                      aria-checked={
                        entry.role === "menuitemradio" ? entry.checked === true : undefined
                      }
                      tabIndex={position === active ? 0 : -1}
                      onClick={() => {
                        close(true);
                        entry.onSelect();
                      }}
                      className="focus-inset flex h-[var(--row-h)] w-full items-center gap-2 rounded-sm px-2 text-start text-body-sm text-fg-1 hover:bg-hover"
                    >
                      {entry.role === "menuitemradio" ? (
                        <Circle
                          aria-hidden="true"
                          size={8}
                          weight="fill"
                          className={cn(
                            "shrink-0",
                            entry.checked === true ? "text-fg-1" : "invisible",
                          )}
                        />
                      ) : EntryIcon === undefined ? null : (
                        <EntryIcon aria-hidden="true" className="shrink-0" />
                      )}
                      <span className="flex-1">{entry.label}</span>
                    </button>
                  );
                })}
              </div>
            ))}
          </div>
        </div>
      ) : null}
      {switching ? (
        <TenantSwitcher
          memberships={memberships}
          openTenantId={openId}
          homePath={homePath}
          built={built}
          onClose={(returnFocus) => {
            setSwitching(false);
            if (returnFocus) {
              trigger.current?.focus();
            }
          }}
        />
      ) : null}
    </span>
  );
}
