// Explain reads, verification and calculation traces (04 §15.3 API-R-49, §16.11 API-S-Explain, §16.14
// API-S-CalcTrace; SCREENS §6.3 to §6.5, SCR-URL-11, §0.4 RT-96; DESIGN_SYSTEM DS-CMP-15; BUILD_SPEC
// CTR-26). The `explain` URL parameter names a figure as `<object_type>~<id>~<measure>` with an optional
// `~<period_key>`. "Verify" is a command whose `Idempotency-Key` comes from the panel's keys; it answers
// `{recomputed_value, stored_value, matches}`, and the panel cites the request id of a mismatch. The trace
// page reads the stored T-ENG-03 document, whose nodes name each input as `{node}` or as
// `{ref_type, ref_id, detail}`.
import messages from "../../../messages/en.json";
import { send } from "../client";
import type { CommandKeys } from "../commands";
import { listSearch } from "../lists";
import { readProblem } from "../problems";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";

export type ExplainOut = components["schemas"]["ExplainOut"];
export type ExplainVerify = components["schemas"]["ExplainVerifyOut"];
export type CalcTrace = components["schemas"]["CalcTraceOut"];

export const EXPLAIN_PATH = "/api/v1/explain";
export const CALC_TRACES_PATH = "/api/v1/calc-traces";
/** SCREENS RT-96 X:trace `/trace/:calcTraceId?node=<node id>`. */
export const TRACE_ROUTE = "/trace";
export const EXPLAIN_PARAM = "explain";
export const TRACE_NODE_PARAM = "node";
/** SCREENS §6.3: the panel binds `depth=6`. */
export const DEFAULT_EXPLAIN_DEPTH = 6;
/** SCREENS §0.4 RT-96: engine figures need `contract.read`, report cells `report.run`. */
export const TRACE_READ_PERMISSIONS: readonly string[] = ["contract.read", "report.run"];

/** 04 §16.11 object types of `GET /explain/{object_type}/{id}/{measure}`. */
export const EXPLAIN_OBJECT_TYPES = [
  "contract_version",
  "obligation",
  "obligation_version",
  "schedule_line",
  "subledger_line",
  "journal_line",
  "contract_version_balance",
  "loss_provision_version",
] as const;
export type ExplainObjectTypeValue = (typeof EXPLAIN_OBJECT_TYPES)[number];

/** The figure an explanation reads: the API-R-49 path and its `period` and `book` parameters. */
export interface ExplainFigure {
  readonly objectType: ExplainObjectTypeValue;
  readonly id: string;
  readonly measure: string;
  readonly periodKey?: string | undefined;
  readonly book?: string | undefined;
}

const SEPARATOR = "~";
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;
const MEASURE = /^[a-z][a-z0-9_]*$/;
const PERIOD_KEY = /^[A-Za-z0-9-]+$/;

/** SCR-URL-11: the `explain` parameter value of a figure. */
export function figureParam(figure: ExplainFigure): string {
  const parts = [figure.objectType, figure.id, figure.measure];
  if (figure.periodKey !== undefined) {
    parts.push(figure.periodKey);
  }
  return parts.join(SEPARATOR);
}

/** SCR-URL-11: the figure of an `explain` parameter, or null when the value is malformed. */
export function parseFigureParam(
  value: string | null,
  book: string | null = null,
): ExplainFigure | null {
  if (value === null) {
    return null;
  }
  const [type, id, measure, periodKey, ...rest] = value.split(SEPARATOR);
  const objectType = EXPLAIN_OBJECT_TYPES.find((item) => item === type);
  if (
    objectType === undefined ||
    id === undefined ||
    measure === undefined ||
    rest.length > 0 ||
    !UUID.test(id) ||
    !MEASURE.test(measure) ||
    (periodKey !== undefined && !PERIOD_KEY.test(periodKey))
  ) {
    return null;
  }
  return { objectType, id, measure, periodKey, book: book ?? undefined };
}

export function explainPath(figure: ExplainFigure): string {
  return `${EXPLAIN_PATH}/${figure.objectType}/${figure.id}/${figure.measure}`;
}

export function explainKey(figure: ExplainFigure, depth = DEFAULT_EXPLAIN_DEPTH): QueryKey {
  return queryKey("explain", "tenant", {
    objectType: figure.objectType,
    id: figure.id,
    measure: figure.measure,
    periodKey: figure.periodKey ?? null,
    book: figure.book ?? null,
    depth,
  });
}

/** API-S-Explain of one figure (SCREENS §6.3 binding). */
export async function fetchExplanation(
  figure: ExplainFigure,
  depth = DEFAULT_EXPLAIN_DEPTH,
): Promise<ExplainOut> {
  const search = listSearch({ period: figure.periodKey, book: figure.book, depth });
  const response = await send("GET", `${explainPath(figure)}${search}`);
  if (!response.ok) {
    throw await readProblem(response);
  }
  return (await response.json()) as ExplainOut;
}

export interface VerifyOutcome {
  readonly result: ExplainVerify;
  /** The request id cited by the mismatch banner (SCREENS §6.4). */
  readonly reference: string | null;
}

/**
 * `POST /explain/{object_type}/{id}/{measure}/verify` (SCREENS §6.3 row 10; 04 API-R-49), under the
 * key `keys` holds for the figure (DG-FE-05 rev 1.156).
 */
export async function verifyExplanation(
  keys: CommandKeys,
  figure: ExplainFigure,
): Promise<VerifyOutcome> {
  const search = listSearch({ period: figure.periodKey, book: figure.book });
  const response = await keys.send("POST", `${explainPath(figure)}/verify${search}`);
  if (!response.ok) {
    throw await readProblem(response);
  }
  // 04 API-R-49: a 202 job carries the same object in `result`.
  const body = (await response.json()) as
    ExplainVerify | { readonly result?: ExplainVerify | null };
  const result = "matches" in body ? body : (body.result ?? null);
  if (result === null) {
    throw new Error("The verification job has no result yet");
  }
  return { result, reference: response.headers.get("X-Request-Id") };
}

export function traceRoute(calcTraceId: string, nodeId?: string): string {
  const search = nodeId === undefined ? "" : `?${TRACE_NODE_PARAM}=${encodeURIComponent(nodeId)}`;
  return `${TRACE_ROUTE}/${calcTraceId}${search}`;
}

export function calcTraceKey(traceId: string): QueryKey {
  return queryKey("calc-traces", "tenant", { id: traceId });
}

/** API-S-CalcTrace: the stored T-ENG-03 row with every node (SCREENS §6.5). */
export async function fetchCalcTrace(traceId: string): Promise<CalcTrace> {
  const response = await send("GET", `${CALC_TRACES_PATH}/${traceId}`);
  if (!response.ok) {
    throw await readProblem(response);
  }
  return (await response.json()) as CalcTrace;
}

export interface TraceSourceRef {
  readonly refType: string;
  readonly refId: string;
}

/** One node of the stored trace document, values at stored precision (DG-KRN-EXP-03). */
export interface TraceNodeRow {
  readonly id: string;
  readonly measure: string;
  readonly value: string;
  readonly currency: string | null;
  readonly formulaId: string;
  readonly roundingResidue: string | null;
  /** Node inputs in trace order. */
  readonly inputs: readonly string[];
  readonly sources: readonly TraceSourceRef[];
}

function text(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

/** The nodes of `trace.nodes`, keyed by id; malformed entries are skipped. */
export function traceNodes(trace: CalcTrace): ReadonlyMap<string, TraceNodeRow> {
  const nodes = new Map<string, TraceNodeRow>();
  const raw = trace.trace.nodes;
  for (const item of Array.isArray(raw) ? (raw as unknown[]) : []) {
    if (typeof item !== "object" || item === null) {
      continue;
    }
    const node = item as Record<string, unknown>;
    const id = text(node.id);
    if (id === null) {
      continue;
    }
    const inputs: string[] = [];
    const sources: TraceSourceRef[] = [];
    for (const input of Array.isArray(node.inputs) ? (node.inputs as unknown[]) : []) {
      if (typeof input !== "object" || input === null) {
        continue;
      }
      const fields = input as Record<string, unknown>;
      const child = text(fields.node);
      const refType = text(fields.ref_type);
      const refId = text(fields.ref_id);
      if (child !== null) {
        inputs.push(child);
      } else if (refType !== null && refId !== null) {
        sources.push({ refType, refId });
      }
    }
    nodes.set(id, {
      id,
      measure: text(node.measure) ?? "",
      value: text(node.value) ?? "",
      currency: text(node.currency),
      formulaId: text(node.formula_id) ?? "",
      roundingResidue: text(node.rounding_residue),
      inputs,
      sources,
    });
  }
  return nodes;
}

/** The top-level rows: the root measures' nodes, else the nodes that no other node takes as input. */
export function traceRoots(trace: CalcTrace, nodes: ReadonlyMap<string, TraceNodeRow>): string[] {
  const named = Object.keys(trace.root_measures)
    .sort()
    .flatMap((key) => [trace.root_measures[key] ?? "", key])
    .filter((id, index, all) => nodes.has(id) && all.indexOf(id) === index);
  if (named.length > 0) {
    return named;
  }
  const referenced = new Set([...nodes.values()].flatMap((node) => node.inputs));
  return [...nodes.keys()].filter((id) => !referenced.has(id));
}

const CATALOGUE: Readonly<Record<string, string>> = messages;

function hasMessage(key: string): boolean {
  return CATALOGUE[key] !== undefined;
}

/** SCREENS §6.3 measure labels: the catalogue key of `explain.measure.<measure>`, when it exists. */
export function measureLabelKey(measure: string): string | null {
  const key = `explain.measure.${measure}`;
  return hasMessage(key) ? key : null;
}

/** SCREENS §6.3 row 3: the sentence and expression keys of a formula id, when the catalogue has both. */
export function formulaKeys(
  formulaId: string,
): { readonly sentence: string; readonly expression: string } | null {
  const sentence = `explain.formula.${formulaId}.sentence`;
  const expression = `explain.formula.${formulaId}.expression`;
  return hasMessage(sentence) && hasMessage(expression) ? { sentence, expression } : null;
}

export interface ExplainDrillHrefs {
  readonly contract_href?: string | null;
  readonly obligation_href?: string | null;
  readonly schedule_lines_href?: string | null;
  readonly subledger_lines_href?: string | null;
}

export type DrillKind = "contract" | "obligation" | "scheduleLines" | "subledgerLines";

const API_CONTRACT = /^\/api\/v1\/contracts\/([0-9a-f-]{36})(?:[/?]|$)/;
const API_OBLIGATION = /^\/api\/v1\/obligations\/([0-9a-f-]{36})(?:[/?]|$)/;
const CONTRACT_PARAM = /[?&]contract=([0-9a-f-]{36})(?:&|$)/;

/**
 * SCREENS §6.3 row 7 drill row, mapped from the API links to the SF-03 routes: "Open contract" and
 * "Schedule lines" to the Obligations and Schedules tabs, "Open obligation" to its pane, and
 * "Subledger lines" to the Journals tab. `search` carries the context parameters.
 */
export function drillRoutes(
  drill: ExplainDrillHrefs,
  search: string,
): { readonly kind: DrillKind; readonly to: string }[] {
  const contractId =
    API_CONTRACT.exec(drill.contract_href ?? "")?.[1] ??
    API_CONTRACT.exec(drill.schedule_lines_href ?? "")?.[1] ??
    CONTRACT_PARAM.exec(drill.subledger_lines_href ?? "")?.[1];
  if (contractId === undefined) {
    return [];
  }
  const base = `/contracts/${contractId}`;
  const routes: { readonly kind: DrillKind; readonly to: string }[] = [];
  if (drill.contract_href !== null && drill.contract_href !== undefined) {
    routes.push({ kind: "contract", to: `${base}/obligations${search}` });
  }
  const obligationId = API_OBLIGATION.exec(drill.obligation_href ?? "")?.[1];
  if (obligationId !== undefined) {
    routes.push({ kind: "obligation", to: `${base}/obligations/${obligationId}${search}` });
  }
  if (drill.schedule_lines_href !== null && drill.schedule_lines_href !== undefined) {
    routes.push({ kind: "scheduleLines", to: `${base}/schedules${search}` });
  }
  if (drill.subledger_lines_href !== null && drill.subledger_lines_href !== undefined) {
    routes.push({ kind: "subledgerLines", to: `${base}/journals${search}` });
  }
  return routes;
}
