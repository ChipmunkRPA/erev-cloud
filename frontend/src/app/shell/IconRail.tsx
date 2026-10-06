// Icon rail (DESIGN_SYSTEM DS-CMP-02; SCREENS SCR-IA-01; 03 REQ-UX-001). The ten D-02 destinations:
// Work, then Govern, then Settings at the bottom. A destination renders only when its default route
// is built (BUILD_SPEC XR-14), and its link carries the context parameters that destination uses. The
// rail collapses to icons with `[` or its toggle; the choice persists under `erev.rail`.
import { useCallback, useEffect, useId, useState } from "react";
import { Link, useLocation } from "react-router";

import {
  CalendarDots,
  ChartBar,
  Database,
  FileText,
  GearSix,
  House,
  type Icon,
  LockKey,
  Notebook,
  Scales,
  SealCheck,
  SidebarSimple,
} from "../../components/icons/registry";
import { Button } from "../../components/ui/Button";
import { cn } from "../../components/ui/cn";
import { Tooltip, type TooltipTriggerProps } from "../../components/ui/Tooltip";
import { isTypingTarget } from "../../lib/a11y/typing";
import { formatNumber } from "../../lib/format";
import { t } from "../../lib/i18n/t";

export type RailGroup = "work" | "govern" | "bottom";
export type ContextParam = "entity" | "period" | "book";

export interface RailDestination {
  readonly key: string;
  readonly labelKey: string;
  readonly icon: Icon;
  readonly group: RailGroup;
  /** The destination SF id (DS-CMP-02). */
  readonly sf: string;
  /** SCREENS SCR-IA-01 default route. */
  readonly defaultRoute: string;
  /** The SF ids whose routes activate the item. */
  readonly activeSf: readonly string[];
  /** Screen ids that activate the item whatever their SF id (the developer settings of SF-16). */
  readonly activeScreens: readonly string[];
  /** SCREENS SCR-IA-01: the context parameters the link carries from the current URL. */
  readonly context: readonly ContextParam[];
  /** DS-CMP-01 go-to sequence, shown in the collapsed tooltip. */
  readonly goTo: string | null;
}

const PILL: readonly ContextParam[] = ["entity", "period", "book"];

export const RAIL_DESTINATIONS: readonly RailDestination[] = [
  {
    key: "home",
    labelKey: "shell.rail.home",
    icon: House,
    group: "work",
    sf: "SF-01",
    defaultRoute: "/home",
    activeSf: ["SF-01"],
    activeScreens: [],
    context: PILL,
    goTo: "G H",
  },
  {
    key: "contracts",
    labelKey: "shell.rail.contracts",
    icon: FileText,
    group: "work",
    sf: "SF-02",
    defaultRoute: "/contracts",
    activeSf: ["SF-02", "SF-03", "SF-07", "SF-18", "SF-20"],
    activeScreens: [],
    context: PILL,
    goTo: "G C",
  },
  {
    key: "schedules",
    labelKey: "shell.rail.schedules",
    icon: CalendarDots,
    group: "work",
    sf: "SF-04",
    defaultRoute: "/schedules",
    activeSf: ["SF-04"],
    activeScreens: [],
    context: PILL,
    goTo: "G S",
  },
  {
    key: "close",
    labelKey: "shell.rail.close",
    icon: LockKey,
    group: "work",
    sf: "SF-05",
    defaultRoute: "/close",
    activeSf: ["SF-05"],
    activeScreens: [],
    context: PILL,
    goTo: "G L",
  },
  {
    key: "journals",
    labelKey: "shell.rail.journals",
    icon: Notebook,
    group: "work",
    sf: "SF-06",
    defaultRoute: "/journals",
    activeSf: ["SF-06"],
    activeScreens: [],
    context: PILL,
    goTo: "G J",
  },
  {
    key: "reports",
    labelKey: "shell.rail.reports",
    icon: ChartBar,
    group: "work",
    sf: "SF-08",
    defaultRoute: "/reports",
    activeSf: ["SF-08", "SF-09", "SF-17"],
    activeScreens: [],
    context: PILL,
    goTo: "G R",
  },
  {
    key: "approvals",
    labelKey: "shell.rail.approvals",
    icon: SealCheck,
    group: "govern",
    sf: "SF-12",
    defaultRoute: "/approvals",
    activeSf: ["SF-12"],
    activeScreens: [],
    context: ["entity"],
    goTo: "G A",
  },
  {
    key: "policies",
    labelKey: "shell.rail.policies",
    icon: Scales,
    group: "govern",
    sf: "SF-13",
    defaultRoute: "/policies",
    activeSf: ["SF-13"],
    activeScreens: [],
    context: [],
    goTo: "G P",
  },
  {
    key: "data",
    labelKey: "shell.rail.data",
    icon: Database,
    group: "govern",
    sf: "SF-10",
    defaultRoute: "/data/imports",
    activeSf: ["SF-10", "SF-11", "SF-19", "SF-16"],
    activeScreens: [],
    context: ["entity"],
    goTo: "G D",
  },
  {
    key: "settings",
    labelKey: "shell.rail.settings",
    icon: GearSix,
    group: "bottom",
    sf: "SF-15",
    defaultRoute: "/settings",
    activeSf: ["SF-14", "SF-15"],
    activeScreens: ["SF-16:developer"],
    context: [],
    goTo: null,
  },
];

export const RAIL_STORAGE_KEY = "erev.rail";

/** SCREENS §1.1 wireframes: expanded at 1440 px and wider, collapsed below, until the user chooses. */
export const RAIL_EXPANDED_MIN_PX = 1440;

function readExpanded(): boolean {
  try {
    const stored = window.localStorage.getItem(RAIL_STORAGE_KEY);
    if (stored === "expanded" || stored === "collapsed") {
      return stored === "expanded";
    }
  } catch {
    // Storage can be unavailable (privacy mode); the width default applies.
  }
  return window.innerWidth >= RAIL_EXPANDED_MIN_PX;
}

function storeExpanded(expanded: boolean): void {
  try {
    window.localStorage.setItem(RAIL_STORAGE_KEY, expanded ? "expanded" : "collapsed");
  } catch {
    // The choice then lasts for this page only.
  }
}

/** The destination that the screen id of the current route activates, if any (DS-CMP-02). */
export function activeDestination(screen: string | null): RailDestination | null {
  if (screen === null) {
    return null;
  }
  const sf = screen.split(":", 1)[0] ?? screen;
  return (
    RAIL_DESTINATIONS.find((destination) => destination.activeScreens.includes(screen)) ??
    RAIL_DESTINATIONS.find((destination) => destination.activeSf.includes(sf)) ??
    null
  );
}

/** The search string of a rail link: the destination's context parameters from the current URL. */
export function contextSearch(search: string, names: readonly ContextParam[]): string {
  const current = new URLSearchParams(search);
  const next = new URLSearchParams();
  for (const name of names) {
    const value = current.get(name);
    if (value !== null && value !== "") {
      next.set(name, value);
    }
  }
  const text = next.toString();
  return text === "" ? "" : `?${text}`;
}

export interface IconRailProps {
  /** The built route paths; a destination renders only when its default route is among them. */
  readonly built: ReadonlySet<string>;
  /** The screen id of the current route (`handle.screen`). */
  readonly activeScreen: string | null;
  /** SCREENS SCR-IA-01 badge: PENDING requests the user can decide; null while unknown. */
  readonly approvalsPending?: number | null;
}

const GROUPS: readonly RailGroup[] = ["work", "govern", "bottom"];

export function IconRail({ built, activeScreen, approvalsPending = null }: IconRailProps) {
  const [expanded, setExpanded] = useState(readExpanded);
  const listId = useId();
  const { search } = useLocation();

  const toggle = useCallback(() => {
    setExpanded((current) => {
      storeExpanded(!current);
      return !current;
    });
  }, []);

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (
        event.key !== "[" ||
        event.defaultPrevented ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        isTypingTarget(event.target)
      ) {
        return;
      }
      event.preventDefault();
      toggle();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => {
      document.removeEventListener("keydown", onKeyDown);
    };
  }, [toggle]);

  const active = activeDestination(activeScreen);
  const groups = GROUPS.map((group) => ({
    group,
    items: RAIL_DESTINATIONS.filter(
      (destination) => destination.group === group && built.has(destination.defaultRoute),
    ),
  })).filter(({ items }) => items.length > 0);
  const wordmark = t("shell.wordmark");

  return (
    <nav
      aria-label={t("shell.rail.label")}
      className={cn(
        "flex h-full shrink-0 flex-col border-e border-hairline bg-surface",
        expanded ? "w-[var(--rail-w-expanded)]" : "w-[var(--rail-w-collapsed)]",
      )}
    >
      <div
        className={cn(
          "flex shrink-0 gap-2 px-2",
          expanded
            ? "h-[var(--topbar-h)] items-center justify-between"
            : "flex-col items-center py-3",
        )}
      >
        {expanded ? (
          <span role="img" aria-label={wordmark} className="ps-2 text-title-md text-fg-1">
            {wordmark}
          </span>
        ) : (
          // DS-BR-04: the monogram tile is the lowercase `e` of the wordmark.
          <span
            role="img"
            aria-label={wordmark}
            className="flex size-6 items-center justify-center rounded-md bg-accent-solid text-title-sm text-on-accent"
          >
            {wordmark.charAt(0)}
          </span>
        )}
        <Button
          variant="ghost"
          icon={SidebarSimple}
          aria-label={t(expanded ? "shell.rail.collapse" : "shell.rail.expand")}
          aria-expanded={expanded}
          aria-controls={listId}
          shortcut="["
          onClick={toggle}
        />
      </div>
      <div id={listId} className="flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto px-2 pb-3">
        {groups.map(({ group, items }, index) => (
          <div
            key={group}
            className={cn(
              "flex flex-col gap-1",
              group === "bottom" ? "mt-auto" : index > 0 && "border-t border-hairline pt-3",
            )}
          >
            {expanded && group !== "bottom" ? (
              <p aria-hidden="true" className="px-3 text-caption text-fg-3">
                {t(`shell.rail.group.${group}`)}
              </p>
            ) : null}
            <ul
              aria-label={group === "bottom" ? undefined : t(`shell.rail.group.${group}`)}
              className="flex flex-col gap-0.5"
            >
              {items.map((destination) => (
                <RailItem
                  key={destination.key}
                  destination={destination}
                  expanded={expanded}
                  active={destination === active}
                  count={destination.key === "approvals" ? approvalsPending : null}
                  search={search}
                />
              ))}
            </ul>
          </div>
        ))}
      </div>
    </nav>
  );
}

interface RailItemProps {
  readonly destination: RailDestination;
  readonly expanded: boolean;
  readonly active: boolean;
  readonly count: number | null;
  readonly search: string;
}

function RailItem({ destination, expanded, active, count, search }: RailItemProps) {
  const label = t(destination.labelKey);
  const badge = count !== null && count > 0;
  const name = badge ? t("shell.rail.pending", { label, count }) : label;
  const ItemIcon = destination.icon;

  const link = (trigger: TooltipTriggerProps | null) => (
    <Link
      to={{
        pathname: destination.defaultRoute,
        search: contextSearch(search, destination.context),
      }}
      aria-label={name}
      aria-current={active ? "page" : undefined}
      onMouseEnter={trigger?.onMouseEnter}
      onMouseLeave={trigger?.onMouseLeave}
      onFocus={trigger?.onFocus}
      onBlur={trigger?.onBlur}
      onKeyDown={trigger?.onKeyDown}
      className={cn(
        "relative flex h-9 items-center gap-3 rounded-md border-s-2 text-body font-medium",
        expanded ? "px-2.5" : "w-9 justify-center",
        active
          ? "border-selection-edge bg-active text-fg-1"
          : "border-transparent text-fg-2 hover:bg-hover hover:text-fg-1",
      )}
    >
      <ItemIcon
        aria-hidden="true"
        size={20}
        weight={active ? "fill" : "regular"}
        className="shrink-0"
      />
      {expanded ? <span className="min-w-0 flex-1 truncate">{label}</span> : null}
      {badge ? (
        <span
          aria-hidden="true"
          className={cn(
            "rounded-full bg-neutral-chip-bg px-1.5 text-caption tabular-nums text-fg-2",
            !expanded && "absolute end-0.5 top-0.5",
          )}
        >
          {formatNumber(count)}
        </span>
      ) : null}
    </Link>
  );

  return (
    <li>
      {expanded ? (
        link(null)
      ) : (
        <Tooltip content={label} shortcut={destination.goTo ?? undefined} kind="label">
          {(trigger) => link(trigger)}
        </Tooltip>
      )}
    </li>
  );
}
