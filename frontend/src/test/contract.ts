// The date contract of mocked traffic (docs/dev-guide.md DG-FE-18, DG-FE-20; supervisor ruling R-65).
// A vitest fixture is only a witness of a page when it has the shape the API sends: a `format:
// date-time` member holding "2026-10-01" let five suites pass while the pages crashed in the browser
// (finding Q-9), and a request body holding a date for a `date-time` member was asserted as correct.
// `contractViolations` reads `docs/api/openapi.json` and checks every JSON body of a mocked exchange:
// a string under a `date` member is `YYYY-MM-DD`, a string under a `date-time` member is RFC 3339 with
// an offset. Routes and statuses the document does not describe are not checked.
import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = dirname(fileURLToPath(import.meta.url));

interface Schema {
  readonly $ref?: string;
  readonly type?: string | readonly string[];
  readonly format?: string;
  readonly properties?: Readonly<Record<string, Schema>>;
  readonly items?: Schema;
  readonly anyOf?: readonly Schema[];
  readonly oneOf?: readonly Schema[];
  readonly allOf?: readonly Schema[];
}

interface Body {
  readonly content?: Readonly<Record<string, { readonly schema?: Schema }>>;
}

interface Operation {
  readonly requestBody?: Body;
  readonly responses?: Readonly<Record<string, Body>>;
}

interface OpenApi {
  readonly components: { readonly schemas: Readonly<Record<string, Schema>> };
  readonly paths: Readonly<Record<string, Readonly<Record<string, Operation>>>>;
}

const DATE = /^\d{4}-\d{2}-\d{2}$/;
const INSTANT = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$/;
const SHAPES = {
  date: { pattern: DATE, words: "a date (YYYY-MM-DD)" },
  "date-time": { pattern: INSTANT, words: "a date-time (RFC 3339 with an offset)" },
} as const;

interface Route {
  readonly template: string;
  readonly pattern: RegExp;
  readonly operations: Readonly<Record<string, Operation>>;
}

let loaded: { readonly document: OpenApi; readonly routes: readonly Route[] } | null = null;

function contract(): { readonly document: OpenApi; readonly routes: readonly Route[] } {
  if (loaded === null) {
    // Resolved as a path: Vite rewrites a literal `new URL("…", import.meta.url)` in DOM suites.
    const file = resolve(HERE, "../../../docs/api/openapi.json");
    const document = JSON.parse(readFileSync(file, "utf8")) as OpenApi;
    const routes = Object.entries(document.paths)
      .map(([template, operations]) => ({
        template,
        pattern: new RegExp(`^${template.replace(/\{[^/]+\}/g, "[^/]+")}$`),
        operations,
      }))
      // A literal segment wins over a path parameter (`/contracts/import` over `/contracts/{id}`).
      .sort((left, right) => holes(left.template) - holes(right.template));
    loaded = { document, routes };
  }
  return loaded;
}

function holes(template: string): number {
  return template.split("{").length - 1;
}

function branches(
  document: OpenApi,
  schema: Schema | undefined,
  seen = new Set<string>(),
): Schema[] {
  if (schema === undefined) {
    return [];
  }
  if (schema.$ref !== undefined) {
    if (seen.has(schema.$ref)) {
      return [];
    }
    const name = schema.$ref.replace("#/components/schemas/", "");
    return branches(document, document.components.schemas[name], new Set(seen).add(schema.$ref));
  }
  const nested = [...(schema.anyOf ?? []), ...(schema.oneOf ?? []), ...(schema.allOf ?? [])];
  return [schema, ...nested.flatMap((branch) => branches(document, branch, seen))];
}

function check(
  document: OpenApi,
  value: unknown,
  schema: Schema | undefined,
  where: string,
): string[] {
  const options = branches(document, schema);
  if (typeof value === "string") {
    const formats = options
      .filter((option) => option.type === "string")
      .map((option) => option.format);
    const dated = formats.filter((format) => format === "date" || format === "date-time");
    // A branch without a date format admits any string.
    if (dated.length === 0 || dated.length < formats.length) {
      return [];
    }
    return dated.some((format) => SHAPES[format].pattern.test(value))
      ? []
      : [
          `${where} ${JSON.stringify(value)} is not ${dated.map((format) => SHAPES[format].words).join(" or ")}`,
        ];
  }
  if (Array.isArray(value)) {
    const items = options.find((option) => option.items !== undefined)?.items;
    return (value as unknown[]).flatMap((element) => check(document, element, items, `${where}[]`));
  }
  if (typeof value === "object" && value !== null) {
    return Object.entries(value).flatMap(([name, member]) => {
      const property = options.find((option) => option.properties?.[name] !== undefined);
      return check(document, member, property?.properties?.[name], `${where}.${name}`);
    });
  }
  return [];
}

function parsed(body: string): unknown {
  if (!body.startsWith("{") && !body.startsWith("[")) {
    return undefined;
  }
  try {
    return JSON.parse(body) as unknown;
  } catch {
    return undefined;
  }
}

function jsonSchema(body: Body | undefined): Schema | undefined {
  const content = body?.content ?? {};
  const media = Object.keys(content).find((type) => type.includes("json"));
  return media === undefined ? undefined : content[media]?.schema;
}

export interface Exchange {
  readonly method: string;
  readonly url: string;
  /** The request body, or the response body when `status` is given. */
  readonly body: string;
  readonly status?: number;
}

/** The members of one mocked request or response whose date shape is not the OpenAPI format. */
export function contractViolations(exchange: Exchange): string[] {
  const value = parsed(exchange.body);
  if (value === undefined) {
    return [];
  }
  const { document, routes } = contract();
  const path = new URL(exchange.url, "http://localhost").pathname;
  const method = exchange.method.toLowerCase();
  const route = routes.find(
    (item) => item.pattern.test(path) && item.operations[method] !== undefined,
  );
  const operation = route?.operations[method];
  if (route === undefined || operation === undefined) {
    return [];
  }
  const schema =
    exchange.status === undefined
      ? jsonSchema(operation.requestBody)
      : jsonSchema(operation.responses?.[String(exchange.status)]);
  const label =
    exchange.status === undefined
      ? `request ${exchange.method} ${route.template}`
      : `${exchange.method} ${route.template} -> ${String(exchange.status)}`;
  return check(document, value, schema, "").map((found) => `${label}: ${found}`);
}
