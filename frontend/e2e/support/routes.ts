// The route list of the crawl (docs/dev-guide.md DG-E2E-13; SCREENS §0.4, SCR-IA-06; supervisor ruling
// R-67 (b)). `readRouter` reads `src/app/router.tsx` as source, so a route added there is crawled
// without an edit here: every object literal with an `id` and a `path` is a route, and a route inside
// `children` takes its parent's path. `readScreenRows` reads the SCREENS §0.4 route table, which names
// the permission of each screen; `screenRowOf` ties a route to its row by screen id, or by the path of
// a redirect the row mentions. Both readers fail on a shape they do not understand instead of
// returning a shorter list.
import { readFileSync } from "node:fs";
import { join } from "node:path";

import ts from "typescript";

import { E2E_DIR } from "./screens";

export const ROUTER_FILE = join(E2E_DIR, "..", "src", "app", "router.tsx");
export const SCREENS_FILE = join(E2E_DIR, "..", "..", "docs", "design", "SCREENS.md");

export interface RouterRoute {
  /** SCR-IA-06: `SF-nn`, `SF-nn:<slug>` or `X:<slug>`. */
  readonly id: string;
  /** The absolute path pattern; `*` for X:not-found. */
  readonly path: string;
  /** The `:name` parameters of the pattern, in order. */
  readonly params: readonly string[];
  /** The route object carries a `loader`, so it redirects and renders no screen of its own. */
  readonly loader: boolean;
}

function propertyOf(
  node: ts.ObjectLiteralExpression,
  name: string,
): ts.PropertyAssignment | undefined {
  return node.properties.find(
    (property): property is ts.PropertyAssignment =>
      ts.isPropertyAssignment(property) &&
      (ts.isIdentifier(property.name) || ts.isStringLiteral(property.name)) &&
      property.name.text === name,
  );
}

/** Reads the routes of a router module; `text` defaults to `src/app/router.tsx`. */
export function readRouter(text = readFileSync(ROUTER_FILE, "utf8")): readonly RouterRoute[] {
  const source = ts.createSourceFile(
    "router.tsx",
    text,
    ts.ScriptTarget.Latest,
    true,
    ts.ScriptKind.TSX,
  );
  // Top-level `const NAME = "…"`: a path or an id written as a constant.
  const constants = new Map<string, string>();
  for (const statement of source.statements) {
    if (!ts.isVariableStatement(statement)) {
      continue;
    }
    for (const declaration of statement.declarationList.declarations) {
      const value = declaration.initializer;
      if (
        ts.isIdentifier(declaration.name) &&
        value !== undefined &&
        (ts.isStringLiteral(value) || ts.isNoSubstitutionTemplateLiteral(value))
      ) {
        constants.set(declaration.name.text, value.text);
      }
    }
  }
  const textOf = (property: ts.PropertyAssignment, where: string): string => {
    const value = property.initializer;
    if (ts.isStringLiteral(value) || ts.isNoSubstitutionTemplateLiteral(value)) {
      return value.text;
    }
    const named = ts.isIdentifier(value) ? constants.get(value.text) : undefined;
    if (named === undefined) {
      throw new Error(
        `${where}: \`${property.getText(source)}\` is neither a string nor a string constant of the module`,
      );
    }
    return named;
  };

  const routes: RouterRoute[] = [];
  let paths = 0;
  const visit = (node: ts.Node, parent: string): void => {
    let base = parent;
    if (ts.isObjectLiteralExpression(node)) {
      const id = propertyOf(node, "id");
      const path = propertyOf(node, "path");
      if (path !== undefined) {
        paths += 1;
        const line = source.getLineAndCharacterOfPosition(path.getStart(source)).line + 1;
        const where = `router.tsx:${String(line)}`;
        if (id === undefined) {
          throw new Error(`${where}: a route object with a path and no id (SCR-IA-06)`);
        }
        const own = textOf(path, where);
        base = own.startsWith("/") || own === "*" ? own : `${parent.replace(/\/+$/, "")}/${own}`;
        routes.push({
          id: textOf(id, where),
          path: base,
          params: [...base.matchAll(/:([A-Za-z]+)/g)].map((match) => match[1] ?? ""),
          loader: propertyOf(node, "loader") !== undefined,
        });
      }
    }
    ts.forEachChild(node, (child) => visit(child, base));
  };
  visit(source, "");

  // Every `path:` of the module is a route above; a shorthand or a spread would not be.
  const written = [...text.matchAll(/^\s*path(?::|,)/gm)].length;
  if (written !== paths) {
    throw new Error(
      `router.tsx writes ${String(written)} path properties and ${String(paths)} were read as routes`,
    );
  }
  const ids = routes.map((route) => route.id);
  const repeated = ids.filter((id, index) => ids.indexOf(id) !== index);
  if (routes.length === 0 || repeated.length > 0) {
    throw new Error(`router.tsx: no route read, or a route id repeats (${repeated.join(", ")})`);
  }
  return routes;
}

export interface ScreenRow {
  /** `RT-nn`. */
  readonly rt: string;
  readonly screen: string;
  /** The path pattern of the row. */
  readonly path: string;
  /** Other path patterns the row names, such as the redirect "`/policies` redirects here". */
  readonly mentions: readonly string[];
  /** The permission cell as written. */
  readonly access: string;
  /** The permission codes of the cell; none for `public` and `authenticated` rows. */
  readonly permissions: readonly string[];
}

const ROW = /^\| (RT-\d+) \| ([^|]+) \| ([^|]+) \| ([^|]*) \| ([^|]*) \| ([^|]+) \| ([^|]*) \|$/;
const CODE_SPAN = /`([^`]+)`/g;
const PERMISSION = /^[a-z_]+\.[a-z_]+$/;

/** Reads the route table of SCREENS §0.4; `text` defaults to the document. */
export function readScreenRows(text = readFileSync(SCREENS_FILE, "utf8")): readonly ScreenRow[] {
  const rows: ScreenRow[] = [];
  for (const line of text.split("\n")) {
    if (!line.startsWith("| RT-")) {
      continue;
    }
    const cells = ROW.exec(line);
    if (cells === null) {
      throw new Error(`SCREENS §0.4: a route row is not seven cells: ${line.slice(0, 80)}`);
    }
    const spans = [...(cells[3] ?? "").matchAll(CODE_SPAN)].map((match) => match[1] ?? "");
    const path = spans[0];
    if (path === undefined) {
      throw new Error(`SCREENS §0.4 ${cells[1] ?? ""}: the path cell names no path`);
    }
    const access = (cells[6] ?? "").trim();
    rows.push({
      rt: cells[1] ?? "",
      screen: (cells[2] ?? "").trim(),
      path,
      mentions: spans.slice(1).filter((span) => span.startsWith("/")),
      access,
      permissions: [...access.matchAll(CODE_SPAN)]
        .map((match) => match[1] ?? "")
        .filter((code) => PERMISSION.test(code)),
    });
  }
  if (rows.length === 0) {
    throw new Error("SCREENS §0.4: no route row read");
  }
  return rows;
}

/** The row of a route: its screen id, else the row that names its path as a redirect. */
export function screenRowOf(route: RouterRoute, rows: readonly ScreenRow[]): ScreenRow | undefined {
  return (
    rows.find((row) => row.screen === route.id) ??
    rows.find((row) => row.mentions.includes(route.path))
  );
}

/** A path pattern as a regular expression over a pathname; parameters match one segment. */
export function patternOf(path: string): RegExp {
  const body = path
    .split("/")
    .map((segment) =>
      segment.startsWith(":") ? "[^/]+" : segment.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"),
    )
    .join("/");
  return new RegExp(`^${body}/?$`);
}

/** The route a pathname lands on: a literal segment wins over a parameter; `*` matches last. */
export function routeAt(pathname: string, routes: readonly RouterRoute[]): RouterRoute | undefined {
  const literal = (route: RouterRoute) =>
    route.path.split("/").filter((part) => !part.startsWith(":")).length;
  return (
    [...routes]
      .filter((route) => route.path !== "*" && patternOf(route.path).test(pathname))
      .sort((left, right) => literal(right) - literal(left))[0] ??
    routes.find((route) => route.path === "*")
  );
}
