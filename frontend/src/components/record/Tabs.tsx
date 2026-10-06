// Tabs (DESIGN_SYSTEM DS-CMP-07). Route tabs are links inside `nav` with aria-current="page" on the
// active link. Panel tabs follow APG Tabs with automatic activation: Left and Right move and activate
// (mirrored in RTL), Home and End go to the first and last tab, and Tab moves into the panel. When tabs
// overflow, the trailing tabs move into a "More" menu; a tab bar never scrolls horizontally. Widths
// come from an invisible measuring copy of every tab, so hidden tabs return when space allows.
import {
  type KeyboardEvent,
  type ReactNode,
  type RefObject,
  useId,
  useLayoutEffect,
  useRef,
  useState,
} from "react";
import { NavLink, useNavigate } from "react-router";

import { formatNumber } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { WarningCircle } from "../icons/registry";
import { cn } from "../ui/cn";
import { Menu, type MenuItem } from "../ui/Menu";
import { Tooltip } from "../ui/Tooltip";

export interface TabItem {
  readonly id: string;
  readonly label: string;
  readonly count?: number | undefined;
  /** The tab holds unresolved blockers: a warning icon, spoken as this text. */
  readonly blockerLabel?: string | undefined;
  readonly disabledReason?: string | undefined;
}

export interface RouteTab extends TabItem {
  readonly to: string;
  /** Active only on the exact path (the record's overview tab). */
  readonly end?: boolean;
}

/** DS-CMP-07: labels 20 px apart (`gap-5`). */
export const TAB_GAP_PX = 20;

/** How many leading tabs fit beside the "More" trigger; every tab when all of them fit. */
export function fittingCount(
  widths: readonly number[],
  moreWidth: number,
  available: number,
): number {
  const total = widths.reduce((sum, width) => sum + width, 0);
  if (total + TAB_GAP_PX * Math.max(widths.length - 1, 0) <= available) {
    return widths.length;
  }
  let used = moreWidth;
  let fitted = 0;
  for (const width of widths) {
    if (used + TAB_GAP_PX + width > available) {
      break;
    }
    used += TAB_GAP_PX + width;
    fitted += 1;
  }
  return fitted;
}

function useVisibleCount(
  bar: RefObject<HTMLElement | null>,
  measure: RefObject<HTMLElement | null>,
  signature: string,
): number {
  const [visible, setVisible] = useState(Number.POSITIVE_INFINITY);
  useLayoutEffect(() => {
    const barElement = bar.current;
    const measureElement = measure.current;
    if (barElement === null || measureElement === null) {
      return undefined;
    }
    const update = () => {
      const widths = Array.from(
        measureElement.querySelectorAll("[data-tab-measure='tab']"),
        (element) => element.getBoundingClientRect().width,
      );
      const more =
        measureElement.querySelector("[data-tab-measure='more']")?.getBoundingClientRect().width ??
        0;
      const available = barElement.getBoundingClientRect().width;
      // A bar without layout (hidden, or not rendered by a browser) keeps every tab.
      setVisible(available > 0 ? fittingCount(widths, more, available) : widths.length);
    };
    update();
    if (typeof ResizeObserver === "undefined") {
      return undefined;
    }
    const observer = new ResizeObserver(update);
    observer.observe(barElement);
    return () => observer.disconnect();
  }, [bar, measure, signature]);
  return visible;
}

/** Changes whenever a measured part of any tab changes, so the widths are measured again. */
function measureSignature(tabs: readonly TabItem[]): string {
  return JSON.stringify(tabs.map((tab) => [tab.label, tab.count, tab.blockerLabel]));
}

function TabLabel({ tab }: { readonly tab: TabItem }) {
  return (
    <>
      <span>{tab.label}</span>
      {/* Spaces between the parts keep the spoken name "Obligations 12"; flex layout drops them. */}
      {tab.count === undefined ? null : (
        <>
          {" "}
          <span className="num text-caption text-fg-3">
            {formatNumber(tab.count, { kind: "count" })}
          </span>
        </>
      )}
      {tab.blockerLabel === undefined ? null : (
        <>
          {" "}
          <WarningCircle aria-hidden="true" className="shrink-0 text-warning-fg" />
          <span className="sr-only">{tab.blockerLabel}</span>
        </>
      )}
    </>
  );
}

function tabClass(active: boolean, disabled: boolean, height: string): string {
  return cn(
    "focus-inset relative inline-flex shrink-0 items-center gap-1.5 whitespace-nowrap rounded-sm text-body-sm font-medium",
    height,
    disabled ? "text-fg-disabled" : active ? "text-fg-1" : "text-fg-2 hover:text-fg-1",
    active &&
      "after:absolute after:inset-x-0 after:bottom-0 after:h-0.5 after:bg-accent-solid after:content-['']",
  );
}

function Measure({
  tabs,
  measure,
}: {
  readonly tabs: readonly TabItem[];
  readonly measure: RefObject<HTMLDivElement | null>;
}) {
  return (
    <div
      aria-hidden="true"
      className="pointer-events-none invisible absolute start-0 top-0 h-0 w-full overflow-hidden"
    >
      <div ref={measure} className="flex w-max gap-5">
        {tabs.map((tab) => (
          <span
            key={tab.id}
            data-tab-measure="tab"
            className="inline-flex items-center gap-1.5 text-body-sm font-medium"
          >
            <TabLabel tab={tab} />
          </span>
        ))}
        <span data-tab-measure="more" className="inline-flex px-2.5 text-body-sm font-medium">
          {t("common.tabs.more")}
        </span>
      </div>
    </div>
  );
}

function DisabledTab({ tab, height }: { readonly tab: TabItem; readonly height: string }) {
  return (
    <Tooltip content={tab.disabledReason ?? ""}>
      {(trigger) => (
        <span
          {...trigger}
          role="link"
          aria-disabled="true"
          tabIndex={0}
          className={tabClass(false, true, height)}
        >
          <TabLabel tab={tab} />
        </span>
      )}
    </Tooltip>
  );
}

export interface RouteTabsProps {
  /** The `nav` name, for example "NS-SO-DE-5004 sections". */
  readonly label: string;
  readonly tabs: readonly RouteTab[];
}

export function RouteTabs({ label, tabs }: RouteTabsProps) {
  const navigate = useNavigate();
  const bar = useRef<HTMLDivElement>(null);
  const measure = useRef<HTMLDivElement>(null);
  const visible = useVisibleCount(bar, measure, measureSignature(tabs));
  const height = "h-[var(--tab-h)]";
  const overflow: MenuItem[] = tabs
    .slice(visible)
    .filter((tab) => tab.disabledReason === undefined)
    .map((tab) => ({ id: tab.id, label: tab.label, onSelect: () => void navigate(tab.to) }));
  return (
    <nav aria-label={label} className="relative border-b border-hairline">
      <div ref={bar} data-tab-bar="" className="flex items-center gap-5">
        {tabs.slice(0, visible).map((tab) =>
          tab.disabledReason === undefined ? (
            <NavLink
              key={tab.id}
              to={tab.to}
              end={tab.end ?? false}
              className={({ isActive }) => tabClass(isActive, false, height)}
            >
              <TabLabel tab={tab} />
            </NavLink>
          ) : (
            <DisabledTab key={tab.id} tab={tab} height={height} />
          ),
        )}
        {overflow.length === 0 ? null : (
          <Menu label={t("common.tabs.more")} variant="ghost" size="sm" items={overflow} />
        )}
      </div>
      <Measure tabs={tabs} measure={measure} />
    </nav>
  );
}

export interface PanelTabsProps {
  /** The tablist name, for example "Obligation sections". */
  readonly label: string;
  readonly tabs: readonly TabItem[];
  readonly selectedId: string;
  readonly onChange: (id: string) => void;
  /** The selected tab's panel content. */
  readonly children: ReactNode;
}

export function PanelTabs({ label, tabs, selectedId, onChange, children }: PanelTabsProps) {
  const base = useId();
  const bar = useRef<HTMLDivElement>(null);
  const measure = useRef<HTMLDivElement>(null);
  const tabRefs = useRef(new Map<string, HTMLButtonElement>());
  const visible = useVisibleCount(bar, measure, measureSignature(tabs));
  const shown = tabs.slice(0, visible);
  const enabled = shown.filter((tab) => tab.disabledReason === undefined);
  const selectedShown = enabled.some((tab) => tab.id === selectedId);
  const tabbable = selectedShown ? selectedId : enabled[0]?.id;
  const tabId = (id: string) => `${base}-tab-${id}`;
  const panelId = `${base}-panel`;
  const height = "h-[var(--control-h)]";

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const current = enabled.findIndex((tab) => tabRefs.current.get(tab.id) === event.target);
    if (current < 0) {
      return;
    }
    const rtl = event.currentTarget.closest("[dir]")?.getAttribute("dir") === "rtl";
    const count = enabled.length;
    let next: number;
    switch (event.key) {
      case rtl ? "ArrowLeft" : "ArrowRight":
        next = (current + 1) % count;
        break;
      case rtl ? "ArrowRight" : "ArrowLeft":
        next = (current - 1 + count) % count;
        break;
      case "Home":
        next = 0;
        break;
      case "End":
        next = count - 1;
        break;
      default:
        return;
    }
    event.preventDefault();
    const tab = enabled[next];
    if (tab !== undefined) {
      onChange(tab.id);
      tabRefs.current.get(tab.id)?.focus();
    }
  };

  const overflow: MenuItem[] = tabs
    .slice(visible)
    .filter((tab) => tab.disabledReason === undefined)
    .map((tab) => ({ id: tab.id, label: tab.label, onSelect: () => onChange(tab.id) }));
  const selectedTab = tabs.find((tab) => tab.id === selectedId);

  return (
    <div className="flex flex-col">
      <div className="relative border-b border-hairline">
        <div
          ref={bar}
          data-tab-bar=""
          role="tablist"
          aria-label={label}
          tabIndex={-1}
          onKeyDown={onKeyDown}
          className="flex items-center gap-5"
        >
          {shown.map((tab) =>
            tab.disabledReason === undefined ? (
              <button
                key={tab.id}
                ref={(element) => {
                  if (element === null) {
                    tabRefs.current.delete(tab.id);
                  } else {
                    tabRefs.current.set(tab.id, element);
                  }
                }}
                id={tabId(tab.id)}
                type="button"
                role="tab"
                aria-selected={tab.id === selectedId}
                aria-controls={tab.id === selectedId ? panelId : undefined}
                tabIndex={tab.id === tabbable ? 0 : -1}
                onClick={() => onChange(tab.id)}
                className={tabClass(tab.id === selectedId, false, height)}
              >
                <TabLabel tab={tab} />
              </button>
            ) : (
              <Tooltip key={tab.id} content={tab.disabledReason}>
                {(trigger) => (
                  <button
                    {...trigger}
                    type="button"
                    role="tab"
                    aria-selected="false"
                    aria-disabled="true"
                    tabIndex={-1}
                    className={tabClass(false, true, height)}
                  >
                    <TabLabel tab={tab} />
                  </button>
                )}
              </Tooltip>
            ),
          )}
          {overflow.length === 0 ? null : (
            <Menu label={t("common.tabs.more")} variant="ghost" size="sm" items={overflow} />
          )}
        </div>
        <Measure tabs={tabs} measure={measure} />
      </div>
      <div
        id={panelId}
        role="tabpanel"
        aria-labelledby={selectedShown ? tabId(selectedId) : undefined}
        aria-label={selectedShown ? undefined : selectedTab?.label}
        tabIndex={0}
        className="focus-inset pt-[var(--panel-pad)]"
      >
        {children}
      </div>
    </div>
  );
}
