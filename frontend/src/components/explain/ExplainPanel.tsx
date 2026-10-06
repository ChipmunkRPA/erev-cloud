// Explain panel (DESIGN_SYSTEM DS-CMP-15; SCREENS §6.1 to §6.4, §6.7, SCR-URL-11; REQ-UX-005; 04 §16.11
// API-S-Explain; BUILD_SPEC CTR-26). A docked `aside` named by the figure heading, which receives focus on
// open. Header: eyebrow, figure name, value, context line, "Copy link" and Close, with the breadcrumb and
// "Back to <figure>" when drilled. Sections, each with an `h3`: Narrative, Formula (catalogue sentence,
// expression and rounding rule), Contributions for a sum by cause, Inputs, Calculation steps, Source records
// with the drill row, Versions and History. Footer: "Verify" and "Open calculation trace". A computed input
// opens its own explanation in the same panel; opening another figure pushes onto the Back stack, and
// `Alt+Left` or Back goes up one level. Esc closes and returns focus to the trigger. The `explain` URL
// parameter follows the current figure (history.replace) and opens the panel on load. A response from
// another calculation version shows the changed banner. The panel carries `data-testid="<SF id>-explain"`
// and each section `<SF id>-explain-<section>` (SCREENS §6.7). A list level (SCREENS §6.3, rev 1.21) has
// no figure of its own: the host provides it under an id, the panel shows its value, the table of its
// entries with a button per entry that opens the entry's explanation on the Back stack, and its
// sentences; it has no footer and no link to copy, and the `explain` parameter is absent while it is
// the current level (SCR-URL-11 names figures).
import { useQuery } from "@tanstack/react-query";
import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { Link, UNSAFE_DataRouterStateContext, useLocation, useNavigate } from "react-router";

import { announce } from "../../lib/a11y/announce";
import { useCommandKeys } from "../../lib/api/commands";
import {
  drillRoutes,
  EXPLAIN_PARAM,
  type ExplainDrillHrefs,
  figureParam,
  formulaKeys,
  measureLabelKey,
  parseFigureParam,
  traceRoute,
  verifyExplanation,
  type VerifyOutcome,
} from "../../lib/api/queries/explain";
import { fetchPeriods, periodLabel, periodsKey } from "../../lib/api/queries/tenant";
import { queryKey } from "../../lib/api/query-keys";
import {
  formatDate,
  formatMoney,
  formatNumber,
  formatPeriod,
  formatTimestamp,
} from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { usePageStays } from "../../lib/url/live-search";
import { Banner } from "../feedback/Banner";
import { Skeleton } from "../feedback/Skeleton";
import { CaretLeft, CopySimple, Function as FunctionIcon, X } from "../icons/registry";
import { Button } from "../ui/Button";
import {
  type ExplainActions,
  ExplainContext,
  type ExplainList,
  type ExplainRequest,
  type FigureRef,
  useExplain,
} from "./ExplainTrigger";

export interface ExplainSourceRef {
  /** 04 §16.11 `ref_type`, for example `contract_event` or `import_row`. */
  readonly ref_type: string;
  readonly ref_id: string;
  readonly label: string;
  /** Null when no route reads the reference. */
  readonly href: string | null;
}

export type ExplainInput = { readonly node_id: string } | ExplainSourceRef;

export interface ExplainNode {
  readonly id: string;
  readonly measure: string;
  readonly value: string;
  readonly currency: string | null;
  /** Null for an input value that is not computed. */
  readonly formula_id: string | null;
  readonly params: Readonly<Record<string, string>>;
  readonly rounding_residue: string | null;
  readonly inputs: readonly ExplainInput[];
}

export interface ExplainHistoryEntry {
  readonly contract_version_id: string;
  readonly version_no: number;
  readonly known_at: string;
  readonly value: string;
  readonly delta: string | null;
  readonly cause: string;
  readonly origin_period_key: string | null;
}

export interface Explanation {
  readonly calc_trace_id: string;
  readonly engine_version: string;
  readonly root_node_id: string;
  readonly nodes: readonly ExplainNode[];
  readonly narrative: readonly string[];
  readonly history: readonly ExplainHistoryEntry[];
  readonly context: {
    readonly as_of: string | null;
    readonly known_at: string | null;
    readonly contract_version_id?: string;
    readonly version_no?: number;
  };
  readonly drill: ExplainDrillHrefs & {
    readonly source_rows: readonly {
      readonly import_upload_id: string;
      readonly sheet: string | null;
      readonly row_number: number;
      readonly href: string;
    }[];
  };
}

export type LoadExplanation = (figure: FigureRef) => Promise<Explanation>;
export type VerifyExplanation = (figure: FigureRef) => Promise<VerifyOutcome>;

interface FigureLevel {
  readonly kind: "figure";
  readonly request: ExplainRequest;
  /** A drilled input node; null for the figure's root node. */
  readonly nodeId: string | null;
  readonly label: string;
  /** Opened from the `explain` URL parameter: the name follows the context calendar (L6-4-Q-2). */
  readonly fromUrl?: boolean;
}

/** A list level as opened: the id of a list the host provides (SCREENS §6.3 list level). */
interface ListEntry {
  readonly kind: "list";
  readonly id: string;
}

/** A list level as shown: the host's current content under that id. */
interface ListLevel extends ListEntry {
  readonly list: ExplainList;
  readonly label: string;
}

type Level = FigureLevel | ListLevel;

interface ExplainState {
  readonly stack: readonly Level[];
  readonly load: LoadExplanation;
  readonly verify: VerifyExplanation;
  readonly traceHref: (calcTraceId: string, nodeId: string) => string;
  readonly linkFor?: ((figure: FigureRef) => string) | undefined;
  readonly onAsk?: ((figure: FigureRef) => void) | undefined;
  /** The SF id of the host screen, for the SCREENS §6.7 test hooks; null outside a data router. */
  readonly screen: string | null;
  readonly drill: (node: ExplainNode) => void;
  readonly back: () => void;
  readonly close: () => void;
}

const ExplainStateContext = createContext<ExplainState | null>(null);

export interface ExplainProviderProps {
  readonly load: LoadExplanation;
  /** "Verify" (API-R-49 `…/verify`); default the API command. */
  readonly verify?: VerifyExplanation | undefined;
  /** The route of the full calculation trace page; default RT-96 with the node selected. */
  readonly traceHref?: ((calcTraceId: string, nodeId: string) => string) | undefined;
  /** The shareable link of a figure; default the current URL, which names the figure. */
  readonly linkFor?: ((figure: FigureRef) => string) | undefined;
  /** "Ask about this figure" renders only when AI is enabled for the tenant. */
  readonly onAsk?: ((figure: FigureRef) => void) | undefined;
  /**
   * The list levels of the host by id (SCREENS §6.3 list level). A level whose id the host no longer
   * provides is not shown.
   */
  readonly lists?: Readonly<Record<string, ExplainList>> | undefined;
  readonly children: ReactNode;
}

function screenOf(handle: unknown): string | null {
  if (typeof handle !== "object" || handle === null) {
    return null;
  }
  const sf = (handle as { readonly sf?: unknown }).sf;
  return typeof sf === "string" && sf !== "X" ? sf : null;
}

function measureLabel(measure: string): string {
  const key = measureLabelKey(measure);
  return key === null ? measure : t(key);
}

/**
 * SCREENS §6.3 row 1: "<measure label> · <period label>". A figure opened from the URL takes its period
 * label from the calendar the context pill loads, else the fiscal label, and has no context line
 * (D-87 L6-4-Q-2).
 */
function figureName(figure: FigureRef, calendarLabel: string | null): string {
  const measure = measureLabel(figure.measure);
  // The DS-CMP-06 meta separator joins two catalogue labels, as the context pill's "<code> · <name>".
  return figure.periodKey === undefined
    ? measure
    : `${measure} · ${calendarLabel ?? formatPeriod(figure.periodKey)}`;
}

export function ExplainProvider({
  load,
  verify: verifyGiven,
  traceHref = traceRoute,
  linkFor,
  onAsk,
  lists,
  children,
}: ExplainProviderProps) {
  const [stack, setStack] = useState<readonly (FigureLevel | ListEntry)[]>([]);
  // "Verify" is a command: its key is the panel's for the figure (DG-FE-05 rev 1.156).
  const keys = useCommandKeys();
  const verify = useMemo<VerifyExplanation>(
    () => verifyGiven ?? ((figure) => verifyExplanation(keys, figure)),
    [verifyGiven, keys],
  );
  const trigger = useRef<HTMLElement | null>(null);
  const restoreFocus = useRef(false);
  const location = useLocation();
  const navigate = useNavigate();
  const stays = usePageStays();
  const routerState = useContext(UNSAFE_DataRouterStateContext);
  const screen = screenOf(routerState?.matches.at(-1)?.route.handle);
  // The `explain` value the URL and the stack last agreed on.
  const synced = useRef<string | null>(null);

  const open = useCallback((request: ExplainRequest, element: HTMLElement | null) => {
    if (element !== null && element.closest("[data-explain-panel]") === null) {
      trigger.current = element;
    }
    setStack((previous) => [
      ...previous,
      { kind: "figure", request, nodeId: null, label: request.label },
    ]);
  }, []);
  const openList = useCallback((id: string, element: HTMLElement | null) => {
    if (element !== null && element.closest("[data-explain-panel]") === null) {
      trigger.current = element;
    }
    setStack((previous) => [...previous, { kind: "list", id }]);
  }, []);
  const drill = useCallback((node: ExplainNode) => {
    setStack((previous) => {
      const current = previous.at(-1);
      return current === undefined || current.kind !== "figure"
        ? previous
        : [
            ...previous,
            {
              kind: "figure",
              request: current.request,
              nodeId: node.id,
              label: measureLabel(node.measure),
            },
          ];
    });
  }, []);
  const back = useCallback(() => {
    setStack((previous) => (previous.length > 1 ? previous.slice(0, -1) : previous));
  }, []);
  const close = useCallback(() => {
    restoreFocus.current = true;
    setStack([]);
  }, []);

  useEffect(() => {
    if (stack.length === 0 && restoreFocus.current) {
      restoreFocus.current = false;
      if (trigger.current?.isConnected === true) {
        trigger.current.focus();
      }
    }
  }, [stack]);

  // The context parameters of the URL, and the figure it names.
  const params = new URLSearchParams(location.search);
  const param = params.get(EXPLAIN_PARAM);
  const book = params.get("book");
  const entity = params.get("entity");
  // L6-4-Q-2: the calendar the context pill loads names a URL-opened figure's period. The provider reads
  // that calendar from the cache and never fetches it; without it the fiscal label stands.
  const calendarQuery = { entity: entity ?? "", book: book ?? "" };
  const calendar = useQuery({
    queryKey: periodsKey(calendarQuery),
    queryFn: () => fetchPeriods(calendarQuery),
    enabled: false,
  });
  const periods = calendar.data;
  const named = useMemo(
    () =>
      stack.flatMap((level): Level[] => {
        if (level.kind === "list") {
          // The host's content as it is now; a list the host no longer provides is not a level.
          const list = lists?.[level.id];
          return list === undefined ? [] : [{ ...level, list, label: list.label }];
        }
        if (level.fromUrl !== true || level.nodeId !== null) {
          return [level];
        }
        const key = level.request.figure.periodKey;
        const found = periods?.find((item) => item.period.period_key === key);
        const label = figureName(
          level.request.figure,
          found === undefined ? null : periodLabel(found.period),
        );
        return [{ ...level, label, request: { ...level.request, label } }];
      }),
    [stack, periods, lists],
  );

  // SCR-URL-11: the URL names the current figure, replaced in place; a list level is no figure.
  const top = named.at(-1);
  const current = top?.kind === "figure" ? top.request.figure : undefined;
  const desired = current === undefined ? null : figureParam(current);
  useEffect(() => {
    if (desired === synced.current) {
      return;
    }
    if (!stays()) {
      // The page is leaving (DG-FE-03 rule (3), rev 1.230): this write names the path that was
      // rendered and would take the member back to it. A figure opened from the page being left is
      // not carried to the next page; a panel closed there is closed by the next page's address.
      if (desired !== null) {
        setStack([]);
      }
      return;
    }
    synced.current = desired;
    const search = new URLSearchParams(location.search);
    if (desired === null) {
      search.delete(EXPLAIN_PARAM);
    } else {
      search.set(EXPLAIN_PARAM, desired);
    }
    const text = search.toString();
    void navigate(
      { pathname: location.pathname, search: text === "" ? "" : `?${text}`, hash: location.hash },
      { replace: true, state: location.state as unknown },
    );
  }, [desired, location, navigate, stays]);

  // A link or history entry that names a figure opens it; one without the parameter closes the panel.
  useEffect(() => {
    if (param === synced.current) {
      return;
    }
    synced.current = param;
    const figure = parseFigureParam(param, book);
    if (figure === null) {
      setStack([]);
      return;
    }
    const label = figureName(figure, null);
    setStack((previous) => [
      ...previous,
      { kind: "figure", request: { figure, label }, nodeId: null, label, fromUrl: true },
    ]);
  }, [param, book]);

  const actions = useMemo<ExplainActions>(() => ({ open, openList }), [open, openList]);
  const state = useMemo<ExplainState>(
    () => ({ stack: named, load, verify, traceHref, linkFor, onAsk, screen, drill, back, close }),
    [named, load, verify, traceHref, linkFor, onAsk, screen, drill, back, close],
  );
  return (
    <ExplainContext.Provider value={actions}>
      <ExplainStateContext.Provider value={state}>{children}</ExplainStateContext.Provider>
    </ExplainContext.Provider>
  );
}

/** Traces longer than this collapse behind "Show all <n> steps". */
export const COLLAPSED_STEPS = 6;

/**
 * SCREENS §6.3 row 4: the per-cause inputs of a sum by cause, the stage 09 `revenue_by_cause` nodes
 * (ENGINE_SPEC_B §9.5). A figure whose inputs are cumulative targets shows no Contributions table.
 */
const CAUSE_MEASURE = "revenue_by_cause";

const ZERO = /^-?0*(\.0*)?$/;

function figureText(value: string, currency: string | null): string {
  // Non-money inputs keep full stored precision, for example an allocation ratio to 18 decimals.
  return currency === null ? value : formatMoney(value, currency, { variant: "inline" });
}

function verifyText(value: string, currency: string | null): string {
  return currency === null
    ? formatNumber(value)
    : formatMoney(value, currency, { variant: "cell" });
}

function decimalPlaces(value: string): number {
  const dot = value.indexOf(".");
  return dot === -1 ? 0 : value.length - dot - 1;
}

function isNodeInput(input: ExplainInput): input is { readonly node_id: string } {
  return "node_id" in input;
}

function causeLabel(node: ExplainNode): string {
  return (
    node.params.label ?? node.params.cause ?? node.params.line_type ?? measureLabel(node.measure)
  );
}

/** The context parameters that drill links keep (SCR-URL-01 to SCR-URL-03). */
function contextSearch(search: string): string {
  const current = new URLSearchParams(search);
  const next = new URLSearchParams();
  for (const name of ["entity", "period", "book"]) {
    const value = current.get(name);
    if (value !== null) {
      next.set(name, value);
    }
  }
  const text = next.toString();
  return text === "" ? "" : `?${text}`;
}

/** The nodes below `root` in depth-first order, each once: the calculation steps. */
function traceSteps(root: ExplainNode, byId: ReadonlyMap<string, ExplainNode>): ExplainNode[] {
  const seen = new Set<string>();
  const steps: ExplainNode[] = [];
  const visit = (node: ExplainNode) => {
    if (seen.has(node.id)) {
      return;
    }
    seen.add(node.id);
    for (const input of node.inputs) {
      const child = isNodeInput(input) ? byId.get(input.node_id) : undefined;
      if (child !== undefined && child.formula_id !== null) {
        visit(child);
      }
    }
    if (node.formula_id !== null) {
      steps.push(node);
    }
  };
  visit(root);
  return steps;
}

function Section({
  title,
  testId,
  children,
}: {
  readonly title: string;
  readonly testId?: string | undefined;
  readonly children: ReactNode;
}) {
  const id = useId();
  return (
    <section aria-labelledby={id} data-testid={testId} className="flex flex-col gap-2">
      <h3 id={id} className="text-title-sm text-fg-1">
        {title}
      </h3>
      {children}
    </section>
  );
}

function Body({
  explanation,
  level,
}: {
  readonly explanation: Explanation;
  readonly level: FigureLevel;
}) {
  const state = useContext(ExplainStateContext);
  const location = useLocation();
  const [allSteps, setAllSteps] = useState(false);
  const byId = useMemo(
    () => new Map(explanation.nodes.map((node) => [node.id, node])),
    [explanation.nodes],
  );
  const node = byId.get(level.nodeId ?? explanation.root_node_id);
  if (state === null || node === undefined) {
    return null;
  }
  const testId = (slug: string) =>
    state.screen === null ? undefined : `${state.screen}-explain-${slug}`;
  const children = node.inputs.flatMap((input) => {
    const child = isNodeInput(input) ? byId.get(input.node_id) : undefined;
    return child === undefined ? [] : [child];
  });
  const sources = node.inputs.filter((input): input is ExplainSourceRef => !isNodeInput(input));
  const steps = traceSteps(node, byId);
  const visibleSteps = allSteps ? steps : steps.slice(0, COLLAPSED_STEPS);
  const root = level.nodeId === null;
  const params = Object.entries(node.params);
  const formula = node.formula_id === null ? null : formulaKeys(node.formula_id);
  const contributions = children.filter((child) => child.measure === CAUSE_MEASURE);
  const sourceRows = root ? explanation.drill.source_rows : [];
  const drill = root ? drillRoutes(explanation.drill, contextSearch(location.search)) : [];
  const version = explanation.context.version_no;

  return (
    <>
      {!root || explanation.narrative.length === 0 ? null : (
        <Section title={t("common.explain.section.narrative")} testId={testId("narrative")}>
          {explanation.narrative.map((sentence) => (
            <p key={sentence} className="text-body-sm text-fg-1">
              {sentence}
            </p>
          ))}
        </Section>
      )}

      <Section title={t("common.explain.section.formula")} testId={testId("formula")}>
        {node.formula_id === null ? (
          <p className="text-body-sm text-fg-2">{t("common.explain.inputValue")}</p>
        ) : (
          <>
            {formula === null ? null : (
              <>
                <p className="text-body-sm text-fg-1">{t(formula.sentence)}</p>
                <code className="block whitespace-pre-wrap break-words rounded-sm bg-subtle px-2 py-1.5 font-mono text-mono-sm text-fg-1">
                  {t(formula.expression)}
                </code>
              </>
            )}
            {node.currency === null ? null : (
              <p className="text-body-sm text-fg-2">
                {t("common.explain.rounding", {
                  places: formatNumber(decimalPlaces(node.value), { kind: "count" }),
                })}
              </p>
            )}
            <p>
              <code className="font-mono text-mono-sm text-fg-3">{node.formula_id}</code>
            </p>
          </>
        )}
      </Section>

      {contributions.length === 0 ? null : (
        <Section title={t("common.explain.section.contributions")} testId={testId("contributions")}>
          <table className="w-full border-collapse text-body-sm">
            <thead>
              <tr className="border-b border-default text-caption text-fg-3">
                <th scope="col" className="py-1 pe-2 text-start font-medium">
                  {t("common.explain.contributions.cause")}
                </th>
                <th scope="col" className="py-1 text-end font-medium">
                  {t("common.explain.contributions.amount")}
                </th>
              </tr>
            </thead>
            <tbody>
              {contributions.map((child) => (
                <tr key={`cause:${child.id}`} className="border-b border-hairline">
                  <th scope="row" className="py-1 pe-2 text-start font-normal">
                    {causeLabel(child)}
                  </th>
                  <td className="num py-1 text-end">{figureText(child.value, child.currency)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Section>
      )}

      {params.length === 0 && children.length === 0 ? null : (
        <Section title={t("common.explain.section.inputs")} testId={testId("inputs")}>
          <table className="w-full border-collapse text-body-sm">
            <thead>
              <tr className="border-b border-default text-caption text-fg-3">
                <th scope="col" className="py-1 pe-2 text-start font-medium">
                  {t("common.explain.column.name")}
                </th>
                <th scope="col" className="py-1 pe-2 text-end font-medium">
                  {t("common.explain.column.value")}
                </th>
                <th scope="col" className="py-1 text-start font-medium">
                  {t("common.explain.column.source")}
                </th>
              </tr>
            </thead>
            <tbody>
              {params.map(([name, value]) => (
                <tr key={`param:${name}`} className="border-b border-hairline">
                  <th
                    scope="row"
                    className="py-1 pe-2 text-start font-mono text-mono-sm font-normal"
                  >
                    {name}
                  </th>
                  <td className="num py-1 pe-2 text-end">{value}</td>
                  <td className="py-1 text-fg-2">{t("common.explain.source.parameter")}</td>
                </tr>
              ))}
              {children.map((child) => {
                const label = measureLabel(child.measure);
                return (
                  <tr key={`node:${child.id}`} className="border-b border-hairline">
                    <th
                      scope="row"
                      className={
                        label === child.measure
                          ? "py-1 pe-2 text-start font-mono text-mono-sm font-normal"
                          : "py-1 pe-2 text-start font-normal"
                      }
                    >
                      {label}
                    </th>
                    <td className="num py-1 pe-2 text-end">
                      {figureText(child.value, child.currency)}
                    </td>
                    <td className="py-1">
                      {child.formula_id === null ? (
                        <span className="text-fg-2">{t("common.explain.source.input")}</span>
                      ) : (
                        <Button
                          variant="ghost"
                          size="sm"
                          icon={FunctionIcon}
                          aria-label={t("common.explain.explainInput", { name: label })}
                          onClick={() => state.drill(child)}
                        />
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Section>
      )}

      {steps.length === 0 ? null : (
        <Section title={t("common.explain.section.steps")} testId={testId("calculation-steps")}>
          <ol className="flex list-decimal flex-col gap-1 ps-5 text-body-sm">
            {visibleSteps.map((step) => (
              <li key={step.id} className="text-fg-1">
                <span>{measureLabel(step.measure)}</span>{" "}
                <code className="font-mono text-mono-sm text-fg-3">{step.formula_id}</code>{" "}
                <span className="num">{figureText(step.value, step.currency)}</span>
                {step.rounding_residue === null || ZERO.test(step.rounding_residue) ? null : (
                  <span className="text-fg-2">
                    {" "}
                    {t("common.explain.step.residue", { value: step.rounding_residue })}
                  </span>
                )}
              </li>
            ))}
          </ol>
          {steps.length > COLLAPSED_STEPS && !allSteps ? (
            <div>
              <Button variant="link" onClick={() => setAllSteps(true)}>
                {t("common.explain.showAllSteps", { count: steps.length })}
              </Button>
            </div>
          ) : null}
        </Section>
      )}

      {sources.length === 0 && sourceRows.length === 0 && drill.length === 0 ? null : (
        <Section title={t("common.explain.section.sources")} testId={testId("source-records")}>
          {sources.length === 0 && sourceRows.length === 0 ? null : (
            <ul className="flex flex-col gap-1 text-body-sm">
              {sources.map((source) => (
                <li key={`${source.ref_type}:${source.ref_id}`}>
                  {source.href === null ? (
                    <span className="text-fg-1">{source.label}</span>
                  ) : (
                    <Link to={source.href} className="text-accent-fg hover:underline">
                      {source.label}
                    </Link>
                  )}
                </li>
              ))}
              {sourceRows.map((row) => (
                <li key={`${row.import_upload_id}:${row.sheet ?? ""}:${String(row.row_number)}`}>
                  <Link to={row.href} className="text-accent-fg hover:underline">
                    {row.sheet === null
                      ? t("common.explain.sourceRowCsv", { row: formatNumber(row.row_number) })
                      : t("common.explain.sourceRow", {
                          row: formatNumber(row.row_number),
                          sheet: row.sheet,
                        })}
                  </Link>
                </li>
              ))}
            </ul>
          )}
          {drill.length === 0 ? null : (
            <nav
              aria-label={t("common.explain.drill.label")}
              className="flex flex-wrap gap-x-3 gap-y-1 text-body-sm"
            >
              {drill.map((link) => (
                <Link key={link.kind} to={link.to} className="text-accent-fg hover:underline">
                  {t(`common.explain.drill.${link.kind}`)}
                </Link>
              ))}
            </nav>
          )}
        </Section>
      )}

      <Section title={t("common.explain.section.versions")} testId={testId("versions")}>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 gap-y-1 text-body-sm">
          <dt className="text-fg-3">{t("common.explain.version.engine")}</dt>
          <dd className="font-mono text-mono-sm text-fg-1">{explanation.engine_version}</dd>
          <dt className="text-fg-3">{t("common.explain.version.trace")}</dt>
          <dd className="break-all font-mono text-mono-sm text-fg-1" data-volatile="">
            {explanation.calc_trace_id}
          </dd>
          {version === undefined ? null : (
            <>
              <dt className="text-fg-3">{t("common.explain.version.contract")}</dt>
              <dd className="break-all text-fg-1" data-volatile="">
                {t("common.explain.version.contractValue", {
                  version: formatNumber(version, { kind: "count" }),
                  id: explanation.context.contract_version_id ?? "",
                })}
              </dd>
            </>
          )}
          <dt className="text-fg-3">{t("common.explain.version.asOf")}</dt>
          <dd className="text-fg-1">
            {/* 04 API-S-Explain `context.as_of` is a business date (ContextOut, format date). */}
            {explanation.context.as_of !== null &&
            /^\d{4}-\d{2}-\d{2}$/.test(explanation.context.as_of)
              ? formatDate(explanation.context.as_of)
              : formatTimestamp(explanation.context.as_of)}
          </dd>
          <dt className="text-fg-3">{t("common.explain.version.knownAt")}</dt>
          <dd className="text-fg-1">{formatTimestamp(explanation.context.known_at)}</dd>
        </dl>
      </Section>

      {!root || explanation.history.length === 0 ? null : (
        <Section title={t("common.explain.section.history")} testId={testId("history")}>
          <ol className="flex flex-col gap-2 border-s border-default ps-3 text-body-sm">
            {explanation.history.map((entry) => (
              <li key={entry.contract_version_id} className="flex flex-col">
                <span className="text-fg-1">
                  {t("common.explain.historyVersion", { version: formatNumber(entry.version_no) })}
                  {" · "}
                  <time dateTime={entry.known_at}>{formatTimestamp(entry.known_at)}</time>
                </span>
                <span className="num text-fg-1">
                  {figureText(entry.value, node.currency)}
                  {entry.delta === null ? "" : ` (${figureText(entry.delta, node.currency)})`}
                </span>
                <span className="font-mono text-mono-sm text-fg-3">
                  {entry.origin_period_key === null
                    ? entry.cause
                    : t("common.explain.historyOrigin", {
                        cause: entry.cause,
                        period: formatPeriod(entry.origin_period_key),
                      })}
                </span>
              </li>
            ))}
          </ol>
        </Section>
      )}
    </>
  );
}

/**
 * SCREENS §6.3 list level (rev 1.21): the entries of a value the trace holds at no node of its own. The
 * table has no total row; the value in the header is the API's figure.
 */
function ListBody({
  list,
  testId,
}: {
  readonly list: ExplainList;
  readonly testId?: string | undefined;
}) {
  const { open } = useExplain();
  let table: ReactNode;
  if (list.error !== undefined) {
    const retry = list.error.onRetry;
    table = (
      <Banner
        tone="negative"
        title={list.error.title}
        headingLevel={4}
        actions={
          <Button variant="link" onClick={retry}>
            {t("common.explain.retry")}
          </Button>
        }
      />
    );
  } else if (list.rows === undefined) {
    table = <Skeleton region={list.caption} shape="rows" count={3} />;
  } else if (list.rows.length === 0) {
    table = <p className="text-body-sm text-fg-2">{list.empty}</p>;
  } else {
    table = (
      <table className="w-full border-collapse text-body-sm">
        <caption className="sr-only">{list.caption}</caption>
        <thead>
          <tr className="border-b border-default text-caption text-fg-3">
            <th scope="col" className="py-1 pe-2 text-start font-medium">
              {list.columns.entry}
            </th>
            <th scope="col" className="py-1 pe-2 text-end font-medium">
              {list.columns.amount}
            </th>
            <th scope="col" className="py-1 text-start font-medium">
              {t("common.explain.column.explain")}
            </th>
          </tr>
        </thead>
        <tbody>
          {list.rows.map((row) => {
            const explain = row.explain;
            return (
              <tr key={row.id} className="border-b border-hairline">
                <th scope="row" className="py-1 pe-2 text-start font-normal">
                  {row.label}
                </th>
                <td className="num py-1 pe-2 text-end">
                  {formatMoney(row.amount, row.currency, { variant: "inline" })}
                </td>
                <td className="py-1">
                  {explain === undefined ? null : (
                    <Button
                      variant="ghost"
                      size="sm"
                      icon={FunctionIcon}
                      aria-label={explain.label}
                      onClick={(event) => open(explain.request, event.currentTarget)}
                    />
                  )}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    );
  }
  return (
    <Section title={list.caption} testId={testId}>
      {list.intro === undefined ? null : <p className="text-body-sm text-fg-1">{list.intro}</p>}
      {table}
      {list.notes}
    </Section>
  );
}

type Verification =
  | { readonly key: string; readonly kind: "pending" }
  | { readonly key: string; readonly kind: "done"; readonly outcome: VerifyOutcome }
  | { readonly key: string; readonly kind: "failed" };

function verificationMessage(outcome: VerifyOutcome, currency: string | null): string {
  const value = verifyText(outcome.result.recomputed_value, currency);
  return outcome.result.matches
    ? t("common.explain.verify.match", { value })
    : t("common.explain.verify.mismatch", {
        value,
        stored: verifyText(outcome.result.stored_value, currency),
        reference: outcome.reference ?? "",
      });
}

export function ExplainPanel() {
  const state = useContext(ExplainStateContext);
  if (state === null) {
    throw new Error("ExplainPanel needs an ExplainProvider (DS-CMP-15)");
  }
  const { stack, load, verify, traceHref, linkFor, onAsk, screen, back, close } = state;
  const level = stack.at(-1);
  const parent = stack.at(-2);
  const titleId = useId();
  const panel = useRef<HTMLElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const [verification, setVerification] = useState<Verification | null>(null);
  const figure = level?.kind === "figure" ? level.request.figure : undefined;
  const query = useQuery({
    queryKey: queryKey("explain", "tenant", {
      objectType: figure?.objectType ?? null,
      id: figure?.id ?? null,
      measure: figure?.measure ?? null,
      periodKey: figure?.periodKey ?? null,
      book: figure?.book ?? null,
    }),
    queryFn: () => {
      if (figure === undefined) {
        throw new Error("No figure to explain");
      }
      return load(figure);
    },
    enabled: figure !== undefined,
  });

  // The levels as opened. Focus follows a level that was pushed or popped, and stays where the reader
  // put it when the content of the same levels is provided again (the host gives a list level its
  // content on every render of its own).
  const shape = stack
    .map((item) =>
      item.kind === "list"
        ? `list:${item.id}`
        : `figure:${figureParam(item.request.figure)}:${item.nodeId ?? ""}`,
    )
    .join("|");
  useEffect(() => {
    if (shape !== "") {
      heading.current?.focus();
    }
  }, [shape]);

  useEffect(() => {
    const element = panel.current;
    if (element === null) {
      return undefined;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.defaultPrevented) {
        return;
      }
      if (event.key === "Escape") {
        event.preventDefault();
        close();
      } else if (event.key === "ArrowLeft" && event.altKey) {
        event.preventDefault();
        back();
      }
    };
    element.addEventListener("keydown", onKeyDown);
    return () => element.removeEventListener("keydown", onKeyDown);
  }, [back, close, level]);

  if (level === undefined) {
    return null;
  }
  const path =
    parent === undefined ? null : (
      <nav aria-label={t("common.explain.path")} className="flex items-center gap-1">
        <Button
          variant="ghost"
          size="sm"
          icon={CaretLeft}
          aria-label={t("common.explain.back", { figure: parent.label })}
          onClick={back}
        />
        <ol className="flex min-w-0 flex-wrap items-center gap-1 text-caption text-fg-3">
          {stack.map((item, index) => (
            <li key={`${String(index)}:${item.label}`} className="flex items-center gap-1">
              {index === 0 ? null : <span aria-hidden="true">›</span>}
              <span aria-current={index === stack.length - 1 ? "page" : undefined}>
                {item.label}
              </span>
            </li>
          ))}
        </ol>
      </nav>
    );
  const closeButton = (
    <Button
      variant="ghost"
      size="sm"
      icon={X}
      aria-label={t("common.dialog.close")}
      onClick={close}
    />
  );
  if (level.kind === "list") {
    const list = level.list;
    return (
      <aside
        ref={panel}
        aria-labelledby={titleId}
        data-explain-panel=""
        data-testid={screen === null ? undefined : `${screen}-explain`}
        className="flex h-full w-[var(--explain-w)] max-w-full shrink-0 flex-col border-s border-hairline bg-raised"
      >
        <div className="flex flex-col gap-2 border-b border-hairline px-[var(--panel-pad)] py-3">
          {path}
          <div className="flex items-start gap-2">
            <div className="flex min-w-0 flex-1 flex-col gap-0.5">
              <span className="text-caption text-fg-3">{t("common.explain.eyebrow")}</span>
              <h2 ref={heading} id={titleId} tabIndex={-1} className="text-title-md text-fg-1">
                {level.label}
              </h2>
              <span className="num text-kpi text-fg-1">
                {formatMoney(list.value, list.currency, { variant: "kpi" })}
              </span>
              {list.context === undefined ? null : (
                <span className="text-body-sm text-fg-2">{list.context}</span>
              )}
            </div>
            {closeButton}
          </div>
        </div>
        <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto p-[var(--panel-pad)]">
          <ListBody
            list={list}
            testId={screen === null ? undefined : `${screen}-explain-by-obligation`}
          />
        </div>
      </aside>
    );
  }
  if (figure === undefined) {
    return null;
  }
  const explanation = query.data;
  const node =
    explanation === undefined
      ? undefined
      : explanation.nodes.find((item) => item.id === (level.nodeId ?? explanation.root_node_id));
  const rootCurrency =
    explanation?.nodes.find((item) => item.id === explanation.root_node_id)?.currency ?? null;
  const changed =
    explanation !== undefined &&
    figure.calcTraceId !== undefined &&
    explanation.calc_trace_id !== figure.calcTraceId;
  const levelKey = `${String(stack.length)}:${level.nodeId ?? ""}`;
  const shown = verification?.key === levelKey ? verification : null;

  const runVerify = () => {
    if (shown?.kind === "pending") {
      return;
    }
    setVerification({ key: levelKey, kind: "pending" });
    verify(figure).then(
      (outcome) => {
        setVerification({ key: levelKey, kind: "done", outcome });
        announce(verificationMessage(outcome, rootCurrency), "polite");
      },
      () => setVerification({ key: levelKey, kind: "failed" }),
    );
  };
  const copyLink = () => {
    const link = linkFor === undefined ? window.location.href : linkFor(figure);
    void navigator.clipboard
      .writeText(new URL(link, window.location.origin).toString())
      .then(() => announce(t("common.explain.linkCopied"), "polite"));
  };

  return (
    <aside
      ref={panel}
      aria-labelledby={titleId}
      data-explain-panel=""
      data-testid={screen === null ? undefined : `${screen}-explain`}
      className="flex h-full w-[var(--explain-w)] max-w-full shrink-0 flex-col border-s border-hairline bg-raised"
    >
      <div className="flex flex-col gap-2 border-b border-hairline px-[var(--panel-pad)] py-3">
        {path}
        <div className="flex items-start gap-2">
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            <span className="text-caption text-fg-3">{t("common.explain.eyebrow")}</span>
            <h2 ref={heading} id={titleId} tabIndex={-1} className="text-title-md text-fg-1">
              {level.label}
            </h2>
            {node === undefined ? null : (
              <span className="num text-kpi text-fg-1">
                {node.currency === null
                  ? node.value
                  : formatMoney(node.value, node.currency, { variant: "kpi" })}
              </span>
            )}
            {level.request.context === undefined ? null : (
              <span className="text-body-sm text-fg-2">{level.request.context}</span>
            )}
          </div>
          <Button
            variant="ghost"
            size="sm"
            icon={CopySimple}
            aria-label={t("common.explain.copyLink")}
            onClick={copyLink}
          />
          {closeButton}
        </div>
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-5 overflow-y-auto p-[var(--panel-pad)]">
        {changed ? (
          <Banner tone="warning" title={t("common.explain.changed")} headingLevel={3} />
        ) : null}
        {query.isError ? (
          <Banner
            tone="negative"
            title={t("common.explain.loadError")}
            headingLevel={3}
            actions={
              <Button variant="link" onClick={() => void query.refetch()}>
                {t("common.explain.retry")}
              </Button>
            }
          />
        ) : explanation === undefined ? (
          <>
            <Skeleton region={t("common.explain.section.formula")} count={2} />
            <Skeleton region={t("common.explain.section.inputs")} shape="rows" count={3} />
            <Skeleton region={t("common.explain.section.steps")} count={3} />
          </>
        ) : (
          <Body key={levelKey} explanation={explanation} level={level} />
        )}
      </div>
      {explanation === undefined ? null : (
        <div className="flex flex-col gap-2 border-t border-hairline px-[var(--panel-pad)] py-3">
          {shown?.kind === "done" ? (
            <Banner
              tone={shown.outcome.result.matches ? "positive" : "negative"}
              title={verificationMessage(shown.outcome, rootCurrency)}
              headingLevel={3}
            />
          ) : shown?.kind === "failed" ? (
            <Banner tone="negative" title={t("common.explain.verify.failed")} headingLevel={3} />
          ) : null}
          <div className="flex flex-wrap items-center gap-3">
            <Button
              size="sm"
              variant="secondary"
              aria-busy={shown?.kind === "pending" ? true : undefined}
              onClick={runVerify}
            >
              {t("common.explain.verify.action")}
            </Button>
            <Link
              to={traceHref(explanation.calc_trace_id, node?.id ?? explanation.root_node_id)}
              className="text-body-sm text-accent-fg hover:underline"
            >
              {t("common.explain.openTrace")}
            </Link>
            {onAsk === undefined ? null : (
              <Button size="sm" onClick={() => onAsk(figure)}>
                {t("common.explain.ask")}
              </Button>
            )}
          </div>
        </div>
      )}
    </aside>
  );
}
