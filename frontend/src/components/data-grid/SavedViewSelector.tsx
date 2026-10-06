// Saved-view selector (DESIGN_SYSTEM DS-CMP-10 "Saved views"; SCREENS SCR-URL-07, SCR-URL-21, SCR-IA-07,
// §3.4 quick lists; 04 API-R-16, T-PLT-37). The trigger names the active view ("View: <name>") and shows a
// dot while the grid differs from the view. The menu (APG Menu with radio items) lists quick lists, "My
// views" and "Shared views", then Save view, Save as new view, Rename, Set as my default and Delete; only
// the owner changes a view. The active view is `view=<id or quick-list literal>` in the URL, its sort,
// quick search and filters are URL parameters, and its columns return through `onApplyColumns`.
import {
  type FormEvent,
  type KeyboardEvent,
  type ReactNode,
  useEffect,
  useId,
  useRef,
  useState,
} from "react";
import { useLocation, useNavigate } from "react-router";

import {
  type SavedView,
  useCreateSavedView,
  useDeleteSavedView,
  useSavedViews,
  useUpdateSavedView,
} from "../../lib/api/queries/saved-views";
import { t } from "../../lib/i18n/t";
import { useLivePath, useLiveSearch } from "../../lib/url/live-search";
import { decodeValue, rawParams, withParams } from "../../lib/url/params";
import { Banner } from "../feedback/Banner";
import { FILTER_PREFIX, QUERY_PARAM } from "../filter-bar/filters";
import { controlClass, Field } from "../form/Field";
import { Switch } from "../form/Switch";
import { CaretDown } from "../icons/registry";
import { Button } from "../ui/Button";
import { cn } from "../ui/cn";
import { Modal } from "../ui/Modal";
import { SORT_PARAM } from "./DataGrid";
import type { GridColumnState } from "./types";

export const VIEW_PARAM = "view";
const CURRENCY_VIEW_PARAM = "currency_view";

export interface QuickList {
  readonly literal: string;
  readonly label: string;
  /** The quick list's default sort (SCREENS §3.4). */
  readonly sort?: string | undefined;
}

/** The T-PLT-37 `config` of a grid view. */
export interface SavedViewConfig {
  /** Visible columns in order. */
  readonly columns: readonly string[];
  readonly widths: Readonly<Record<string, number>>;
  readonly pinned: { readonly start: readonly string[]; readonly end: readonly string[] };
  readonly sort: string | null;
  /** Raw `f.<field>` values by field. */
  readonly filters: Readonly<Record<string, string>>;
  readonly query: string;
  readonly currency_view: string | null;
  /** The owner's default view of the screen. */
  readonly is_default?: boolean;
}

export interface SavedViewSelectorProps {
  /** SCREENS SCR-IA-07 screen code, for example `SF-02`. */
  readonly screenCode: string;
  /** The signed-in member (`/me` `active_membership_id`); only the owner changes a view. */
  readonly membershipId: string | null;
  /** The default view's name, for example "All contracts". */
  readonly defaultLabel: string;
  readonly quickLists?: readonly QuickList[] | undefined;
  readonly columnState: GridColumnState;
  readonly defaultColumnState: GridColumnState;
  readonly onApplyColumns: (state: GridColumnState) => void;
  /** The tenant view-sharing permission. */
  readonly canShare?: boolean;
  readonly testId?: string | undefined;
}

type Dialog = "saveAs" | "rename" | "delete" | null;

function isRecord(value: unknown): value is Readonly<Record<string, unknown>> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function strings(value: unknown): readonly string[] | null {
  return Array.isArray(value) && value.every((item) => typeof item === "string")
    ? (value as string[])
    : null;
}

function withDefault(config: SavedViewConfig, flag: boolean): SavedViewConfig {
  return {
    columns: config.columns,
    widths: config.widths,
    pinned: config.pinned,
    sort: config.sort,
    filters: config.filters,
    query: config.query,
    currency_view: config.currency_view,
    ...(flag ? { is_default: true } : {}),
  };
}

/** A stored config read defensively; missing members take the screen default. */
export function readConfig(
  raw: Readonly<Record<string, unknown>>,
  fallback: GridColumnState,
): SavedViewConfig {
  const pinned = isRecord(raw.pinned) ? raw.pinned : {};
  const widths = isRecord(raw.widths)
    ? Object.fromEntries(
        Object.entries(raw.widths).filter(
          (entry): entry is [string, number] => typeof entry[1] === "number",
        ),
      )
    : {};
  const filters = isRecord(raw.filters)
    ? Object.fromEntries(
        Object.entries(raw.filters).filter(
          (entry): entry is [string, string] => typeof entry[1] === "string",
        ),
      )
    : {};
  return withDefault(
    {
      columns: strings(raw.columns) ?? fallback.order.filter((id) => !fallback.hidden.includes(id)),
      widths,
      pinned: {
        start: strings(pinned.start) ?? fallback.pinned.start,
        end: strings(pinned.end) ?? fallback.pinned.end,
      },
      sort: typeof raw.sort === "string" ? raw.sort : null,
      filters,
      query: typeof raw.query === "string" ? raw.query : "",
      currency_view: typeof raw.currency_view === "string" ? raw.currency_view : null,
    },
    raw.is_default === true,
  );
}

/** The config of the grid as it stands: URL parameters plus column state. */
export function configOf(search: string, state: GridColumnState): SavedViewConfig {
  const params = rawParams(search);
  const value = (name: string) => {
    const param = params.find((item) => item.name === name);
    return param === undefined ? null : decodeValue(param.value);
  };
  return {
    columns: state.order.filter((id) => !state.hidden.includes(id)),
    widths: state.widths,
    pinned: state.pinned,
    sort: value(SORT_PARAM),
    filters: Object.fromEntries(
      params
        .filter((param) => param.name.startsWith(FILTER_PREFIX))
        .map((param) => [param.name.slice(FILTER_PREFIX.length), param.value]),
    ),
    query: value(QUERY_PARAM) ?? "",
    currency_view: value(CURRENCY_VIEW_PARAM),
  };
}

export function columnStateOf(config: SavedViewConfig, fallback: GridColumnState): GridColumnState {
  const extra = fallback.order.filter((id) => !config.columns.includes(id));
  return {
    order: [...config.columns, ...extra],
    hidden: extra,
    widths: config.widths,
    pinned: config.pinned,
  };
}

function entries<T>(record: Readonly<Record<string, T>>): [string, T][] {
  return Object.entries(record).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
}

function comparable(config: SavedViewConfig): string {
  return JSON.stringify([
    config.columns,
    entries(config.widths),
    config.pinned.start,
    config.pinned.end,
    config.sort,
    entries(config.filters),
    config.query,
    config.currency_view,
  ]);
}

export function SavedViewSelector({
  screenCode,
  membershipId,
  defaultLabel,
  quickLists = [],
  columnState,
  defaultColumnState,
  onApplyColumns,
  canShare = false,
  testId,
}: SavedViewSelectorProps) {
  const location = useLocation();
  const navigate = useNavigate();
  // "Save view" and "Delete" answer after an awaited command. A view belongs to the screen, not to
  // the record of the page, so the answer is written only while the page that sent the command is
  // still the one on screen, and onto the search the router holds then (RPT-VIEWER-LATE-RUN-1).
  const livePath = useLivePath();
  const liveSearch = useLiveSearch();
  const shown = useRef(false);
  useEffect(() => {
    shown.current = true;
    return () => {
      shown.current = false;
    };
  }, []);
  const menuId = useId();
  const formId = useId();
  const views = useSavedViews(screenCode);
  const [open, setOpen] = useState(false);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [name, setName] = useState("");
  const [nameError, setNameError] = useState<string | null>(null);
  const [shared, setShared] = useState(false);
  const [unrecognised, setUnrecognised] = useState(false);
  const trigger = useRef<HTMLButtonElement>(null);
  const menu = useRef<HTMLDivElement>(null);
  const appliedDefault = useRef(false);

  const viewParam = (() => {
    const param = rawParams(location.search).find((item) => item.name === VIEW_PARAM);
    return param === undefined ? null : decodeValue(param.value);
  })();
  const list = views.data ?? [];
  const own = (view: SavedView) => membershipId !== null && view.membership_id === membershipId;
  const isDefault = (view: SavedView) =>
    readConfig(view.config, defaultColumnState).is_default === true;
  const mine = list.filter(own);
  const others = list.filter((view) => !own(view));
  const activeView = list.find((view) => view.id === viewParam);
  const activeQuick = quickLists.find((item) => item.literal === viewParam);
  const defaultConfig = configOf("", defaultColumnState);
  const baseline =
    activeView === undefined
      ? { ...defaultConfig, sort: activeQuick?.sort ?? null }
      : readConfig(activeView.config, defaultColumnState);
  const current = configOf(location.search, columnState);
  const dirty = comparable(current) !== comparable(baseline);
  const activeName = activeView?.name ?? activeQuick?.label ?? defaultLabel;
  const owned = activeView !== undefined && own(activeView);
  const previousDefault = mine.find((view) => view.id !== activeView?.id && isDefault(view));

  const create = useCreateSavedView();
  const update = useUpdateSavedView(activeView?.id ?? null);
  const clearDefault = useUpdateSavedView(previousDefault?.id ?? null);
  const remove = useDeleteSavedView(activeView?.id ?? null);

  const apply = (viewId: string | null, config: SavedViewConfig, replace = false) => {
    const changes: Record<string, string | null> = {
      [VIEW_PARAM]: viewId === null ? null : encodeURIComponent(viewId),
      [SORT_PARAM]: config.sort === null ? null : encodeURIComponent(config.sort),
      [QUERY_PARAM]: config.query === "" ? null : encodeURIComponent(config.query),
      [CURRENCY_VIEW_PARAM]:
        config.currency_view === null ? null : encodeURIComponent(config.currency_view),
    };
    for (const [field, raw] of Object.entries(config.filters)) {
      changes[`${FILTER_PREFIX}${field}`] = raw;
    }
    void navigate({ search: withParams(location.search, changes, [FILTER_PREFIX]) }, { replace });
    onApplyColumns(columnStateOf(config, defaultColumnState));
  };

  // SCR-URL-21: an unknown `view` is dropped with the banner once the views have loaded.
  const unknownView =
    viewParam !== null && views.isSuccess && activeView === undefined && activeQuick === undefined;
  useEffect(() => {
    if (unknownView) {
      setUnrecognised(true);
      void navigate(
        { search: withParams(location.search, { [VIEW_PARAM]: null }) },
        { replace: true },
      );
    }
  }, [unknownView, location.search, navigate]);

  // The owner's default view opens when the link carries no grid state.
  useEffect(() => {
    if (appliedDefault.current || !views.isSuccess) {
      return;
    }
    appliedDefault.current = true;
    const modified = rawParams(location.search).some(
      (param) =>
        param.name === SORT_PARAM ||
        param.name === QUERY_PARAM ||
        param.name.startsWith(FILTER_PREFIX),
    );
    // SCR-URL-07: a link naming a saved view and no other grid parameter opens the view as saved.
    if (activeView !== undefined && !modified) {
      apply(activeView.id, readConfig(activeView.config, defaultColumnState), true);
      return;
    }
    const gridState = modified || viewParam !== null;
    const ownDefault = mine.find(isDefault);
    if (ownDefault !== undefined && !gridState) {
      apply(ownDefault.id, readConfig(ownDefault.config, defaultColumnState), true);
    }
  });

  const close = (returnFocus: boolean) => {
    setOpen(false);
    if (returnFocus) {
      trigger.current?.focus();
    }
  };

  useEffect(() => {
    const root = menu.current;
    if (!open || root === null) {
      return undefined;
    }
    const checked = root.querySelector<HTMLElement>("[role='menuitemradio'][aria-checked='true']");
    (checked ?? root.querySelector<HTMLElement>("[role^='menuitem']"))?.focus();
    const onPointerDown = (event: PointerEvent) => {
      const target = event.target;
      if (
        target instanceof Node &&
        !root.contains(target) &&
        trigger.current?.contains(target) !== true
      ) {
        setOpen(false);
      }
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [open]);

  const onMenuKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const items = Array.from(
      menu.current?.querySelectorAll<HTMLElement>("[role^='menuitem']") ?? [],
    );
    const index = items.findIndex((item) => item === document.activeElement);
    const count = items.length;
    let next: number | null = null;
    switch (event.key) {
      case "ArrowDown":
        next = (index + 1) % count;
        break;
      case "ArrowUp":
        next = (index - 1 + count) % count;
        break;
      case "Home":
        next = 0;
        break;
      case "End":
        next = count - 1;
        break;
      case "Escape":
        event.preventDefault();
        event.stopPropagation();
        close(true);
        return;
      case "Tab":
        close(false);
        return;
      default:
        return;
    }
    event.preventDefault();
    items[next]?.focus();
  };

  const openDialog = (next: Dialog) => {
    setName(next === "rename" ? (activeView?.name ?? "") : "");
    setNameError(null);
    setShared(false);
    create.reset();
    update.reset();
    remove.reset();
    setDialog(next);
  };

  const saveView = async () => {
    if (activeView !== undefined) {
      await update.submit({ config: withDefault(current, baseline.is_default === true) });
    }
  };

  const setAsDefault = async () => {
    if (activeView === undefined) {
      return;
    }
    if (previousDefault !== undefined) {
      await clearDefault.submit({
        config: withDefault(readConfig(previousDefault.config, defaultColumnState), false),
      });
    }
    await update.submit({ config: withDefault(baseline, true) });
  };

  const submitName = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const trimmed = name.trim();
    if (trimmed === "") {
      setNameError(t("common.views.nameRequired"));
      return;
    }
    if (dialog === "rename") {
      const outcome = await update.submit({ name: trimmed });
      if (outcome.kind === "succeeded") {
        setDialog(null);
      }
      return;
    }
    const sentFrom = livePath();
    const outcome = await create.submit({
      screen_code: screenCode,
      name: trimmed,
      config: withDefault(current, false),
      is_shared: canShare && shared,
      is_favourite: false,
    });
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      setDialog(null);
      if (shown.current && livePath() === sentFrom) {
        void navigate({
          search: withParams(liveSearch(), { [VIEW_PARAM]: encodeURIComponent(outcome.data.id) }),
        });
      }
    }
  };

  const submitDelete = async () => {
    const sentFrom = livePath();
    const outcome = await remove.submit();
    if (outcome.kind === "succeeded") {
      setDialog(null);
      if (shown.current && livePath() === sentFrom) {
        void navigate({ search: withParams(liveSearch(), { [VIEW_PARAM]: null }) });
      }
    }
  };

  const itemClass =
    "focus-inset flex h-[var(--row-h)] w-full shrink-0 items-center gap-2 rounded-sm px-2 text-start text-body-sm hover:bg-hover";
  const radio = (
    key: string,
    label: string,
    checked: boolean,
    onSelect: () => void,
    caption?: string,
  ) => (
    <button
      key={key}
      type="button"
      role="menuitemradio"
      aria-checked={checked}
      tabIndex={-1}
      onClick={() => {
        close(true);
        onSelect();
      }}
      className={cn(itemClass, "text-fg-1")}
    >
      <span
        aria-hidden="true"
        className={cn(
          "size-1.5 shrink-0 rounded-full",
          checked ? "bg-accent-solid" : "bg-transparent",
        )}
      />
      <span className="min-w-0 flex-1 truncate">{label}</span>
      {caption === undefined ? null : <span className="text-caption text-fg-3">{caption}</span>}
    </button>
  );
  const action = (key: string, label: string, onSelect: () => void, destructive = false) => (
    <button
      key={key}
      type="button"
      role="menuitem"
      tabIndex={-1}
      onClick={() => {
        close(true);
        onSelect();
      }}
      className={cn(itemClass, destructive ? "text-negative-fg" : "text-fg-1")}
    >
      {label}
    </button>
  );
  const group = (key: string, label: string, children: ReactNode) => (
    <div key={key} role="group" aria-labelledby={`${menuId}-${key}`} className="flex flex-col">
      <div id={`${menuId}-${key}`} className="px-2 pb-1 pt-2 text-caption text-fg-3">
        {label}
      </div>
      {children}
    </div>
  );
  const viewRadio = (view: SavedView) =>
    radio(
      view.id,
      view.name,
      view.id === activeView?.id,
      () => apply(view.id, readConfig(view.config, defaultColumnState)),
      isDefault(view) && own(view) ? t("common.views.defaultCaption") : undefined,
    );
  const defaultRadio = radio("default", defaultLabel, viewParam === null, () =>
    apply(null, defaultConfig),
  );

  return (
    <>
      <span className="relative inline-flex">
        <Button
          ref={trigger}
          variant="ghost"
          size="sm"
          trailingIcon={CaretDown}
          aria-label={t(dirty ? "common.views.triggerUnsaved" : "common.views.trigger", {
            name: activeName,
          })}
          aria-haspopup="menu"
          aria-expanded={open}
          aria-controls={open ? menuId : undefined}
          data-testid={testId}
          onClick={() => (open ? close(false) : setOpen(true))}
        >
          {activeName}
          {dirty ? (
            <span aria-hidden="true" className="size-1.5 shrink-0 rounded-full bg-accent-solid" />
          ) : null}
        </Button>
        {open ? (
          <div
            ref={menu}
            id={menuId}
            role="menu"
            aria-label={t("common.views.menuLabel")}
            tabIndex={-1}
            onKeyDown={onMenuKeyDown}
            className="absolute start-0 top-full z-[var(--z-popover)] mt-1 flex max-h-96 min-w-60 flex-col overflow-y-auto rounded-lg border border-hairline bg-raised p-1 shadow-popover"
          >
            {quickLists.length === 0
              ? defaultRadio
              : group("quick", t("common.views.quickLists"), [
                  defaultRadio,
                  ...quickLists.map((item) =>
                    radio(item.literal, item.label, item.literal === viewParam, () =>
                      apply(item.literal, { ...defaultConfig, sort: item.sort ?? null }),
                    ),
                  ),
                ])}
            {mine.length === 0 ? null : group("mine", t("common.views.mine"), mine.map(viewRadio))}
            {others.length === 0
              ? null
              : group("shared", t("common.views.shared"), others.map(viewRadio))}
            <div role="separator" className="my-1 h-px shrink-0 bg-hairline" />
            {owned && dirty ? action("save", t("common.views.save"), () => void saveView()) : null}
            {action("save-as", t("common.views.saveAs"), () => openDialog("saveAs"))}
            {owned ? action("rename", t("common.views.rename"), () => openDialog("rename")) : null}
            {owned && activeView !== undefined && !isDefault(activeView)
              ? action("default", t("common.views.setDefault"), () => void setAsDefault())
              : null}
            {owned
              ? action("delete", t("common.views.delete"), () => openDialog("delete"), true)
              : null}
          </div>
        ) : null}
      </span>
      {unrecognised ? (
        <span className="w-full">
          <Banner
            tone="warning"
            announce="live"
            title={t("common.filters.unrecognised")}
            onDismiss={() => setUnrecognised(false)}
          />
        </span>
      ) : null}
      <Modal
        open={dialog === "saveAs" || dialog === "rename"}
        variant="form"
        title={t(dialog === "rename" ? "common.views.renameTitle" : "common.views.saveAs")}
        primaryAction={{
          label: t(dialog === "rename" ? "common.views.renameConfirm" : "common.views.save"),
          form: formId,
        }}
        submitting={create.pending || update.pending}
        onClose={() => setDialog(null)}
      >
        <form
          id={formId}
          noValidate
          onSubmit={(event) => void submitName(event)}
          className="flex flex-col gap-3"
        >
          <Field
            name="saved-view-name"
            label={t("common.views.name")}
            required
            error={
              nameError ?? (dialog === "rename" ? update.fieldErrors.name : create.fieldErrors.name)
            }
          >
            {(control) => (
              <input
                {...control}
                type="text"
                autoComplete="off"
                value={name}
                onChange={(event) => {
                  setName(event.target.value);
                  setNameError(null);
                }}
                className={controlClass(control["aria-invalid"] === true)}
              />
            )}
          </Field>
          {canShare && dialog === "saveAs" ? (
            <Switch label={t("common.views.share")} checked={shared} onChange={setShared} />
          ) : null}
        </form>
      </Modal>
      <Modal
        open={dialog === "delete"}
        variant="confirmation"
        title={t("common.views.deleteTitle", { name: activeView?.name ?? "" })}
        description={t("common.views.deleteDescription")}
        primaryAction={{
          label: t("common.views.deleteConfirm"),
          destructive: true,
          onAction: () => void submitDelete(),
        }}
        submitting={remove.pending}
        onClose={() => setDialog(null)}
      />
    </>
  );
}
