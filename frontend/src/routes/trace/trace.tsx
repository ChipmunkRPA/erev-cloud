// X:trace Calculation trace (SCREENS §6.5, §0.4 RT-96 `/trace/:calcTraceId?node=<node id>`; 04 API-R-49
// `GET /calc-traces/{id}`, §16.14 API-S-CalcTrace; DESIGN_SYSTEM DS-CMP-10 treegrid, DS-A11Y-11; BUILD_SPEC
// CTR-26). `h1` "Calculation trace", the meta row, and the T-ENG-03 DAG as an APG treegrid with the columns
// Node (measure label indented by depth, with the node id), Formula, Value at full precision, Currency,
// Rounding residue, Inputs (count) and Source. The top rows are the trace's root measures; a node's node
// inputs are its children. `?node=` expands the path to that node and selects it. Toolbar "Expand all",
// "Collapse all" and "Download JSON" (the response body as `trace-<id prefix>.json`). States: 10 skeleton
// rows; SCR-ST-05 "Could not load the calculation trace"; SCR-ST-07 "Calculation trace not found".
// [J] The treegrid is built in this page with the DS-CMP-10 ARIA rows and cells, because the shared
// DataGrid has no tree mode and the trace is one bounded document rather than a paged list. Rows take the
// focus (APG treegrid row mode): Up and Down move, Right expands or enters, Left collapses or goes to the
// parent, Home and End go to the first and last row, Enter toggles.
import { useQuery } from "@tanstack/react-query";
import { type KeyboardEvent, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { Skeleton } from "../../components/feedback/Skeleton";
import { CaretDown, CaretRight, DownloadSimple } from "../../components/icons/registry";
import { Button } from "../../components/ui/Button";
import { ApiProblem } from "../../lib/api/problems";
import {
  type CalcTrace,
  calcTraceKey,
  fetchCalcTrace,
  measureLabelKey,
  TRACE_NODE_PARAM,
  TRACE_READ_PERMISSIONS,
  type TraceNodeRow,
  traceNodes,
  traceRoots,
} from "../../lib/api/queries/explain";
import { useMe } from "../../lib/api/queries/me";
import { formatList, formatNumber, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";

/** Levels shown below a root (04 API-R-49 `depth` maximum). */
const MAX_TREE_DEPTH = 20;
/** "Expand all" stops adding rows beyond this count. */
const EXPAND_ALL_ROW_LIMIT = 5000;
const INDENT_PX = 16;
/** Node, Formula, Value, Currency, Rounding residue, Inputs, Source; the node id truncates. */
const COLUMNS = "minmax(16rem, 1fr) 14rem 8rem 4.5rem 8rem 4rem 10rem";
const GRID_MIN_WIDTH = "64.5rem";

interface TreeRow {
  /** The path of node ids from the root, joined by "/". */
  readonly key: string;
  readonly node: TraceNodeRow;
  readonly depth: number;
  readonly parentKey: string | null;
  readonly expandable: boolean;
  readonly expanded: boolean;
  readonly position: number;
  readonly setSize: number;
}

function childIds(
  node: TraceNodeRow,
  nodes: ReadonlyMap<string, TraceNodeRow>,
  ancestors: ReadonlySet<string>,
): string[] {
  return node.inputs.filter((id) => nodes.has(id) && !ancestors.has(id));
}

function visibleRows(
  nodes: ReadonlyMap<string, TraceNodeRow>,
  roots: readonly string[],
  expanded: ReadonlySet<string>,
): TreeRow[] {
  const rows: TreeRow[] = [];
  const visit = (
    ids: readonly string[],
    depth: number,
    parentKey: string | null,
    ancestors: ReadonlySet<string>,
  ) => {
    ids.forEach((id, index) => {
      const node = nodes.get(id);
      if (node === undefined) {
        return;
      }
      const key = parentKey === null ? id : `${parentKey}/${id}`;
      const children = childIds(node, nodes, ancestors);
      const expandable = children.length > 0 && depth <= MAX_TREE_DEPTH;
      const open = expandable && expanded.has(key);
      rows.push({
        key,
        node,
        depth,
        parentKey,
        expandable,
        expanded: open,
        position: index + 1,
        setSize: ids.length,
      });
      if (open) {
        visit(children, depth + 1, key, new Set([...ancestors, id]));
      }
    });
  };
  visit(roots, 1, null, new Set());
  return rows;
}

function allExpandable(
  nodes: ReadonlyMap<string, TraceNodeRow>,
  roots: readonly string[],
): Set<string> {
  const keys = new Set<string>();
  let count = 0;
  const visit = (
    ids: readonly string[],
    depth: number,
    parentKey: string | null,
    ancestors: ReadonlySet<string>,
  ) => {
    for (const id of ids) {
      const node = nodes.get(id);
      if (node === undefined || count >= EXPAND_ALL_ROW_LIMIT) {
        return;
      }
      count += 1;
      const key = parentKey === null ? id : `${parentKey}/${id}`;
      const children = childIds(node, nodes, ancestors);
      if (children.length > 0 && depth <= MAX_TREE_DEPTH) {
        keys.add(key);
        visit(children, depth + 1, key, new Set([...ancestors, id]));
      }
    }
  };
  visit(roots, 1, null, new Set());
  return keys;
}

/** The shortest path of node ids from a root to `target`, or null when no root reaches it. */
function pathTo(
  nodes: ReadonlyMap<string, TraceNodeRow>,
  roots: readonly string[],
  target: string,
): string[] | null {
  const queue: string[][] = roots.filter((id) => nodes.has(id)).map((id) => [id]);
  const seen = new Set(roots);
  while (queue.length > 0) {
    const path = queue.shift();
    const last = path?.at(-1);
    if (path === undefined || last === undefined) {
      break;
    }
    if (last === target) {
      return path;
    }
    for (const child of nodes.get(last)?.inputs ?? []) {
      if (nodes.has(child) && !seen.has(child)) {
        seen.add(child);
        queue.push([...path, child]);
      }
    }
  }
  return null;
}

function measureLabel(measure: string): string {
  const key = measureLabelKey(measure);
  return key === null ? measure : t(key);
}

function download(trace: CalcTrace): void {
  const blob = new Blob([`${JSON.stringify(trace, null, 2)}\n`], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `trace-${trace.id.slice(0, 8)}.json`;
  document.body.append(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function CalculationTrace() {
  const { calcTraceId = "" } = useParams();
  const [search] = useSearchParams();
  const navigate = useNavigate();
  const me = useMe();
  const permitted = (me.data?.permissions ?? []).some((code) =>
    TRACE_READ_PERMISSIONS.includes(code),
  );
  const trace = useQuery({
    queryKey: calcTraceKey(calcTraceId),
    queryFn: () => fetchCalcTrace(calcTraceId),
    enabled: permitted,
    retry: (count, error) => !(error instanceof ApiProblem && error.status === 404) && count < 2,
  });
  const title = t("explain.trace.title");

  let content;
  if (me.isError) {
    content = <Banner tone="negative" title={me.error.message} headingLevel={2} />;
  } else if (me.data === undefined) {
    content = <Skeleton region={title} shape="rows" count={10} />;
  } else if (!permitted) {
    content = (
      <EmptyState
        title={t("settings.access.title", { area: t("explain.trace.access.area") })}
        description={t("settings.access.description", {
          permission: t("explain.trace.access.permission"),
        })}
        headingLevel={2}
      />
    );
  } else if (trace.error !== null) {
    content =
      trace.error instanceof ApiProblem && trace.error.status === 404 ? (
        <EmptyState
          title={t("explain.trace.notFound.title")}
          description={t("explain.trace.notFound.description")}
          headingLevel={2}
          action={{
            label: t("explain.trace.notFound.action"),
            onAction: () => void navigate("/contracts"),
          }}
        />
      ) : (
        <Banner
          tone="negative"
          title={t("explain.trace.loadError")}
          headingLevel={2}
          actions={
            <Button variant="link" onClick={() => void trace.refetch()}>
              {t("explain.trace.retry")}
            </Button>
          }
        />
      );
  } else if (trace.data === undefined) {
    content = <Skeleton region={title} shape="rows" count={10} />;
  } else {
    content = (
      <TraceView
        key={`${trace.data.id}:${search.get(TRACE_NODE_PARAM) ?? ""}`}
        trace={trace.data}
        selectedNode={search.get(TRACE_NODE_PARAM)}
      />
    );
  }

  return (
    <div data-testid="X-page" className="flex h-full min-h-0 flex-col gap-3">
      <h1 tabIndex={-1} className="text-title-lg text-fg-1">
        {title}
      </h1>
      {content}
    </div>
  );
}

function TraceView({
  trace,
  selectedNode,
}: {
  readonly trace: CalcTrace;
  readonly selectedNode: string | null;
}) {
  const nodes = useMemo(() => traceNodes(trace), [trace]);
  const initial = useMemo(() => {
    const roots = traceRoots(trace, nodes);
    if (selectedNode === null || !nodes.has(selectedNode)) {
      return { roots, expanded: new Set<string>(), selectedKey: null };
    }
    const path = pathTo(nodes, roots, selectedNode);
    if (path === null) {
      // A figure outside the root measures' subtrees is listed first.
      return {
        roots: [selectedNode, ...roots],
        expanded: new Set<string>(),
        selectedKey: selectedNode,
      };
    }
    const keys = path.map((_, index) => path.slice(0, index + 1).join("/"));
    return { roots, expanded: new Set(keys.slice(0, -1)), selectedKey: keys.at(-1) ?? null };
  }, [trace, nodes, selectedNode]);
  const [expanded, setExpanded] = useState<ReadonlySet<string>>(initial.expanded);
  const rows = useMemo(
    () => visibleRows(nodes, initial.roots, expanded),
    [nodes, initial.roots, expanded],
  );
  const [focusKey, setFocusKey] = useState<string | null>(initial.selectedKey);
  const rowRefs = useRef(new Map<string, HTMLDivElement>());
  const grid = useRef<HTMLDivElement>(null);
  const tabbable = rows.some((row) => row.key === focusKey) ? focusKey : (rows[0]?.key ?? null);

  useEffect(() => {
    if (initial.selectedKey === null) {
      return;
    }
    const row = rowRefs.current.get(initial.selectedKey);
    if (row !== undefined && typeof row.scrollIntoView === "function") {
      row.scrollIntoView({ block: "center" });
    }
  }, [initial.selectedKey]);

  useEffect(() => {
    if (tabbable === null || grid.current?.contains(document.activeElement) !== true) {
      return;
    }
    rowRefs.current.get(tabbable)?.focus();
  }, [tabbable]);

  const toggle = (key: string, open: boolean) => {
    setExpanded((previous) => {
      const next = new Set(previous);
      if (open) {
        next.add(key);
      } else {
        next.delete(key);
      }
      return next;
    });
  };

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const index = rows.findIndex((row) => row.key === tabbable);
    const row = rows[index];
    if (row === undefined) {
      return;
    }
    const move = (next: number) => {
      const target = rows[Math.min(Math.max(next, 0), rows.length - 1)];
      if (target !== undefined) {
        setFocusKey(target.key);
        rowRefs.current.get(target.key)?.focus();
      }
    };
    switch (event.key) {
      case "ArrowDown":
        move(index + 1);
        break;
      case "ArrowUp":
        move(index - 1);
        break;
      case "Home":
        move(0);
        break;
      case "End":
        move(rows.length - 1);
        break;
      case "ArrowRight":
        if (row.expandable && !row.expanded) {
          toggle(row.key, true);
        } else if (row.expanded) {
          move(index + 1);
        }
        break;
      case "ArrowLeft":
        if (row.expanded) {
          toggle(row.key, false);
        } else if (row.parentKey !== null) {
          move(rows.findIndex((candidate) => candidate.key === row.parentKey));
        }
        break;
      case "Enter":
        if (row.expandable) {
          toggle(row.key, !row.expanded);
        }
        break;
      default:
        return;
    }
    event.preventDefault();
  };

  const headerCell = "px-2 py-1.5 text-body-sm font-medium text-fg-2";
  const cell = "min-w-0 px-2 py-1.5";
  return (
    <>
      <dl
        aria-label={t("explain.trace.meta.label")}
        className="flex flex-wrap gap-x-6 gap-y-1 text-body-sm"
      >
        <div className="flex gap-2">
          <dt className="text-fg-3">{t("explain.trace.meta.engineVersion")}</dt>
          <dd className="font-mono text-mono-sm text-fg-1">{trace.engine_version}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-fg-3">{t("explain.trace.meta.contractVersion")}</dt>
          <dd className="font-mono text-mono-sm text-fg-1" data-volatile="">
            {trace.contract_version_id}
          </dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-fg-3">{t("explain.trace.meta.book")}</dt>
          <dd className="font-mono text-mono-sm text-fg-1">{trace.book}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-fg-3">{t("explain.trace.meta.nodes")}</dt>
          <dd className="num text-fg-1">{formatNumber(trace.node_count, { kind: "count" })}</dd>
        </div>
        <div className="flex gap-2">
          <dt className="text-fg-3">{t("explain.trace.meta.trace")}</dt>
          <dd className="font-mono text-mono-sm text-fg-1" data-volatile="">
            {trace.id}
          </dd>
        </div>
      </dl>
      <section
        data-testid="X-grid-trace"
        aria-label={t("explain.trace.title")}
        className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-md border border-hairline bg-surface"
      >
        <div className="flex flex-wrap items-center gap-2 border-b border-hairline p-2">
          <Button
            size="sm"
            variant="secondary"
            onClick={() => setExpanded(allExpandable(nodes, initial.roots))}
          >
            {t("explain.trace.expandAll")}
          </Button>
          <Button size="sm" variant="secondary" onClick={() => setExpanded(new Set())}>
            {t("explain.trace.collapseAll")}
          </Button>
          <Button
            size="sm"
            variant="secondary"
            icon={DownloadSimple}
            onClick={() => download(trace)}
          >
            {t("explain.trace.download")}
          </Button>
        </div>
        <div className="min-h-0 flex-1 overflow-auto">
          <div
            ref={grid}
            role="treegrid"
            aria-label={t("explain.trace.title")}
            aria-rowcount={rows.length + 1}
            aria-colcount={7}
            tabIndex={-1}
            onKeyDown={onKeyDown}
            className="text-grid text-fg-1"
            style={{ minInlineSize: GRID_MIN_WIDTH }}
          >
            <div role="rowgroup" className="sticky top-0 z-[var(--z-sticky)]">
              <div
                role="row"
                aria-rowindex={1}
                className="grid border-b border-default bg-subtle"
                style={{ gridTemplateColumns: COLUMNS }}
              >
                <div role="columnheader" aria-colindex={1} className={headerCell}>
                  {t("explain.trace.column.node")}
                </div>
                <div role="columnheader" aria-colindex={2} className={headerCell}>
                  {t("explain.trace.column.formula")}
                </div>
                <div role="columnheader" aria-colindex={3} className={`${headerCell} text-end`}>
                  {t("explain.trace.column.value")}
                </div>
                <div role="columnheader" aria-colindex={4} className={headerCell}>
                  {t("explain.trace.column.currency")}
                </div>
                <div role="columnheader" aria-colindex={5} className={`${headerCell} text-end`}>
                  {t("explain.trace.column.residue")}
                </div>
                <div role="columnheader" aria-colindex={6} className={`${headerCell} text-end`}>
                  {t("explain.trace.column.inputs")}
                </div>
                <div role="columnheader" aria-colindex={7} className={headerCell}>
                  {t("explain.trace.column.source")}
                </div>
              </div>
            </div>
            <div role="rowgroup">
              {rows.map((row, index) => {
                const label = measureLabel(row.node.measure);
                const selected = row.key === initial.selectedKey;
                return (
                  <div
                    key={row.key}
                    ref={(element) => {
                      if (element === null) {
                        rowRefs.current.delete(row.key);
                      } else {
                        rowRefs.current.set(row.key, element);
                      }
                    }}
                    role="row"
                    aria-rowindex={index + 2}
                    aria-level={row.depth}
                    aria-posinset={row.position}
                    aria-setsize={row.setSize}
                    aria-expanded={row.expandable ? row.expanded : undefined}
                    aria-selected={selected ? true : undefined}
                    tabIndex={row.key === tabbable ? 0 : -1}
                    onFocus={() => setFocusKey(row.key)}
                    className={
                      selected
                        ? "focus-inset grid border-b border-hairline bg-accent-subtle"
                        : "focus-inset grid border-b border-hairline bg-surface hover:bg-hover"
                    }
                    style={{ gridTemplateColumns: COLUMNS }}
                  >
                    <div
                      role="rowheader"
                      aria-colindex={1}
                      className={`${cell} flex items-center gap-1.5`}
                      style={{ paddingInlineStart: `${String(8 + (row.depth - 1) * INDENT_PX)}px` }}
                    >
                      {row.expandable ? (
                        <button
                          type="button"
                          tabIndex={-1}
                          aria-label={t(
                            row.expanded ? "explain.trace.collapseRow" : "explain.trace.expandRow",
                            { name: label },
                          )}
                          onClick={() => toggle(row.key, !row.expanded)}
                          className="inline-flex shrink-0 rounded-sm text-fg-3 hover:text-fg-1"
                        >
                          {row.expanded ? (
                            <CaretDown aria-hidden="true" size={12} />
                          ) : (
                            <CaretRight aria-hidden="true" size={12} />
                          )}
                        </button>
                      ) : (
                        <span aria-hidden="true" className="inline-block w-3 shrink-0" />
                      )}
                      <span
                        className={
                          label === row.node.measure
                            ? "shrink-0 font-mono text-mono-sm text-fg-1"
                            : "shrink-0 text-fg-1"
                        }
                      >
                        {label}
                      </span>
                      <span className="truncate font-mono text-mono-sm text-fg-3">
                        {row.node.id}
                      </span>
                    </div>
                    <div
                      role="gridcell"
                      aria-colindex={2}
                      className={`${cell} truncate font-mono text-mono-sm`}
                    >
                      {row.node.formulaId}
                    </div>
                    <div role="gridcell" aria-colindex={3} className={`${cell} num text-end`}>
                      {row.node.value}
                    </div>
                    <div
                      role="gridcell"
                      aria-colindex={4}
                      className={`${cell} font-mono text-mono-sm`}
                    >
                      {row.node.currency ?? NO_VALUE}
                    </div>
                    <div role="gridcell" aria-colindex={5} className={`${cell} num text-end`}>
                      {row.node.roundingResidue ?? NO_VALUE}
                    </div>
                    <div role="gridcell" aria-colindex={6} className={`${cell} num text-end`}>
                      {formatNumber(row.node.inputs.length + row.node.sources.length, {
                        kind: "count",
                      })}
                    </div>
                    <div
                      role="gridcell"
                      aria-colindex={7}
                      className={`${cell} truncate font-mono text-mono-sm text-fg-2`}
                    >
                      {/* Reference data: the stored `ref_type` and the id prefix of each source. */}
                      {row.node.sources.length === 0
                        ? NO_VALUE
                        : formatList(
                            row.node.sources.map(
                              (source) => `${source.refType} ${source.refId.slice(0, 8)}`,
                            ),
                            "unit",
                          )}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </section>
    </>
  );
}
