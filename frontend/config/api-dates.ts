// API date flow (docs/dev-guide.md DG-FE-20; DESIGN_SYSTEM DS-FMT-16, DS-FMT-17): which API fields reach
// the business-date and the instant functions of `src/lib/format`. openapi-typescript types `format:
// date` and `format: date-time` alike as `string`, so the compiler cannot tell them apart; this module
// asks the TypeScript checker where the argument of each such call comes from and reads the format of
// that field in `docs/api/openapi.json`.
//
// Followed: members of API-typed values (resolved on the type of the value that flows in, not on the
// annotation at the use), `const` and `let` variables, destructuring, `??`, `||` and conditional
// branches, component props and object members through every expression assigned to them, function
// parameters through every call site, array callbacks and array methods, the returns of a called
// function, and `useState` through its initial value and every call of its setter. A hand-written
// interface that mirrors an API shape resolves by member name when every schema of the document gives
// that name one date format. Anything else is reported as untraced.
//
// The write direction is checked where it can be seen: a member of an object literal that is typed by an
// API schema (a request body annotated or `satisfies` its `...In` type) and whose OpenAPI format is `date`
// or `date-time` is a use of its own, so a business date assigned to a `date-time` member is a mismatch.
// A body passed untyped is not seen.
import { readFileSync } from "node:fs";
import { relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import ts from "typescript";

export type DateFormat = "date" | "date-time";

export interface FormatRoles {
  /** Exports whose first argument is a `YYYY-MM-DD` business date. */
  readonly dateSinks: readonly string[];
  /** Exports whose first argument is an RFC 3339 instant. */
  readonly instantSinks: readonly string[];
  /** Exports that return a business date. */
  readonly dateProducers: readonly string[];
  /** Exports that return an RFC 3339 instant. */
  readonly instantProducers: readonly string[];
  /** Exports that take an options object: the named member is a business date. */
  readonly dateOptions: Readonly<Record<string, string>>;
  /** Type aliases of the format module whose `value` member is a business date. */
  readonly dateResults: readonly string[];
  /** Components that report a business date through the named callback prop. */
  readonly dateCallbacks: Readonly<Record<string, string>>;
  /** Source files (from `frontend/`) whose own calls are not checked. */
  readonly trusted: readonly string[];
}

export interface Origin {
  /**
   * `field`: an API property and its OpenAPI format; `produced`: a business date by construction;
   * `constant`: a literal; `client`: a URL parameter; `untraced`: not followed.
   */
  readonly kind: "field" | "produced" | "constant" | "client" | "untraced";
  readonly text: string;
  readonly format?: string;
}

export interface SinkUse {
  /** Path from `frontend/`. */
  readonly file: string;
  readonly line: number;
  /** The function, `column kind "date"` for a grid column value, or `member <Schema.member>`. */
  readonly sink: string;
  readonly argument: string;
  readonly wants: DateFormat;
  readonly origins: readonly Origin[];
}

export interface DateFlow {
  /** The exported functions of the format module. */
  readonly formatExports: readonly string[];
  readonly uses: readonly SinkUse[];
}

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

interface Parameter {
  readonly name: string;
  readonly in: string;
  readonly schema?: Schema;
}

interface Operation {
  readonly operationId?: string;
  readonly parameters?: readonly Parameter[];
}

interface OpenApi {
  readonly components: { readonly schemas: Readonly<Record<string, Schema>> };
  readonly paths: Readonly<Record<string, Readonly<Record<string, Operation>>>>;
}

const FRONTEND = fileURLToPath(new URL("..", import.meta.url));
const SOURCE_DIR = resolve(FRONTEND, "src");
const SCHEMA_FILE = resolve(SOURCE_DIR, "lib/api/schema.d.ts");
const FORMAT_MODULE = resolve(SOURCE_DIR, "lib/format/index.ts");
const MIRROR_DIR = resolve(SOURCE_DIR, "lib/api/queries");
const OPENAPI_DOCUMENT = resolve(FRONTEND, "../docs/api/openapi.json");

/** Array methods whose callback receives an element as its first parameter. */
const ELEMENT_CALLBACKS: ReadonlySet<string> = new Set([
  "every",
  "filter",
  "find",
  "findLast",
  "flatMap",
  "forEach",
  "map",
  "some",
]);
/** Array methods that return the elements of the receiver. */
const SAME_ELEMENTS: ReadonlySet<string> = new Set([
  "filter",
  "reverse",
  "slice",
  "sort",
  "toReversed",
  "toSorted",
]);
/** Array methods that return one element of the receiver. */
const ONE_ELEMENT: ReadonlySet<string> = new Set(["at", "find", "findLast"]);
/** Array methods whose callback receives the accumulated value, then an element. */
const REDUCERS: ReadonlySet<string> = new Set(["reduce", "reduceRight"]);
const MAX_DEPTH = 24;

function isProductSource(fileName: string): boolean {
  return (
    fileName.startsWith(`${SOURCE_DIR}/`) &&
    !fileName.startsWith(`${SOURCE_DIR}/test/`) &&
    !/\.test\.tsx?$/.test(fileName)
  );
}

/** The `src` program of `frontend/tsconfig.json` without tests, plus `overlay` files (path → text). */
function createProgram(overlay: ReadonlyMap<string, string>): ts.Program {
  const parsed = ts.getParsedCommandLineOfConfigFile(
    resolve(FRONTEND, "tsconfig.json"),
    {},
    {
      ...ts.sys,
      onUnRecoverableConfigFileDiagnostic: (diagnostic) => {
        throw new Error(ts.flattenDiagnosticMessageText(diagnostic.messageText, "\n"));
      },
    },
  );
  if (parsed === undefined) {
    throw new Error("frontend/tsconfig.json could not be read");
  }
  const host = ts.createCompilerHost(parsed.options, true);
  const readFile = host.readFile.bind(host);
  const fileExists = host.fileExists.bind(host);
  const getSourceFile = host.getSourceFile.bind(host);
  host.readFile = (name) => overlay.get(name) ?? readFile(name);
  host.fileExists = (name) => overlay.has(name) || fileExists(name);
  host.getSourceFile = (name, languageVersion, onError, shouldCreate) => {
    const text = overlay.get(name);
    return text === undefined
      ? getSourceFile(name, languageVersion, onError, shouldCreate)
      : ts.createSourceFile(name, text, languageVersion, true);
  };
  return ts.createProgram({
    rootNames: [...parsed.fileNames.filter(isProductSource), ...overlay.keys()],
    options: parsed.options,
    host,
  });
}

class Formats {
  private readonly document: OpenApi;
  private readonly operations = new Map<string, readonly Parameter[]>();
  private readonly byName = new Map<string, Set<string>>();

  constructor() {
    this.document = JSON.parse(readFileSync(OPENAPI_DOCUMENT, "utf8")) as OpenApi;
    for (const item of Object.values(this.document.paths)) {
      const shared = (item.parameters ?? []) as readonly Parameter[];
      for (const operation of Object.values(item)) {
        if (typeof operation.operationId === "string") {
          this.operations.set(operation.operationId, [...(operation.parameters ?? []), ...shared]);
        }
      }
    }
    for (const schema of Object.values(this.document.components.schemas)) {
      for (const [name, property] of Object.entries(schema.properties ?? {})) {
        const known = this.byName.get(name) ?? new Set<string>();
        for (const format of this.formatsOf([property])) {
          known.add(format);
        }
        this.byName.set(name, known);
      }
    }
  }

  private deref(schema: Schema | undefined): Schema | undefined {
    let current = schema;
    const seen = new Set<string>();
    while (current?.$ref !== undefined && !seen.has(current.$ref)) {
      seen.add(current.$ref);
      current = this.document.components.schemas[current.$ref.replace("#/components/schemas/", "")];
    }
    return current;
  }

  /** The schema, the branches of its `anyOf`, `oneOf` and `allOf`, and its array items. */
  private branches(schema: Schema | undefined): Schema[] {
    const resolved = this.deref(schema);
    if (resolved === undefined) {
      return [];
    }
    const found = [resolved];
    for (const branch of [
      ...(resolved.anyOf ?? []),
      ...(resolved.oneOf ?? []),
      ...(resolved.allOf ?? []),
    ]) {
      found.push(...this.branches(branch));
    }
    if (resolved.items !== undefined) {
      found.push(...this.branches(resolved.items));
    }
    return found;
  }

  /** `date`, `date-time`, another string format, `string` (no format) or `<type>` of a non-string. */
  private formatsOf(schemas: readonly (Schema | undefined)[]): Set<string> {
    const formats = new Set<string>();
    for (const branch of schemas.flatMap((schema) => this.branches(schema))) {
      const types = typeof branch.type === "string" ? [branch.type] : (branch.type ?? []);
      for (const type of types) {
        if (type === "string") {
          formats.add(branch.format ?? "string");
        } else if (type !== "null" && type !== "array") {
          formats.add(`<${type}>`);
        }
      }
    }
    return formats;
  }

  /** The formats of a property declared in `schema.d.ts`, from its path of names. */
  ofDeclaration(path: readonly string[]): { readonly label: string; readonly formats: string[] } {
    const [root, second, third, fourth, fifth] = path;
    if (root === "components" && second === "schemas" && third !== undefined) {
      let schemas: (Schema | undefined)[] = [this.document.components.schemas[third]];
      for (const name of path.slice(3)) {
        schemas = schemas
          .flatMap((schema) => this.branches(schema))
          .map((branch) => branch.properties?.[name])
          .filter((property) => property !== undefined);
      }
      return { label: path.slice(2).join("."), formats: [...this.formatsOf(schemas)].sort() };
    }
    if (root === "operations" && third === "parameters" && second !== undefined) {
      const parameters = (this.operations.get(second) ?? []).filter(
        (parameter) => parameter.in === fourth && parameter.name === fifth,
      );
      return {
        label: `${second}?${fifth ?? ""}`,
        formats: [...this.formatsOf(parameters.map((parameter) => parameter.schema))].sort(),
      };
    }
    return { label: path.join("."), formats: [] };
  }

  /** The one date format every schema of the document gives a property name, if there is one. */
  ofName(name: string): DateFormat | null {
    const formats = [...(this.byName.get(name) ?? [])];
    const [only] = formats;
    return formats.length === 1 && (only === "date" || only === "date-time") ? only : null;
  }
}

/**
 * Where a value comes from: the expression the trace stopped at (typed, so that a member can be
 * resolved on it), whether the value is an element of that array, and what the value is when known.
 */
interface Flow {
  readonly node: ts.Node;
  readonly element: boolean;
  readonly origin?: Origin;
}

interface Trace {
  readonly depth: number;
  readonly active: Set<ts.Node>;
}

class Tracer {
  private readonly checker: ts.TypeChecker;
  private readonly formats = new Formats();
  private readonly sources: readonly ts.SourceFile[];
  private readonly sinks = new Map<
    ts.Symbol,
    { readonly name: string; readonly wants: DateFormat }
  >();
  private readonly producers = new Map<
    ts.Symbol,
    { readonly name: string; readonly format: DateFormat }
  >();
  private readonly optionSinks = new Map<
    ts.Symbol,
    { readonly name: string; readonly member: string }
  >();
  private readonly assigned = new Map<ts.Node, ts.Expression[]>();
  private readonly passed = new Map<ts.Node, ts.Expression[]>();
  private readonly calls = new Map<ts.Symbol, ts.Expression[]>();
  private readonly reassigned = new Map<ts.Symbol, ts.Expression[]>();
  private readonly escaped = new Set<ts.Symbol>();
  private readonly dateSetters = new Set<ts.Symbol>();
  readonly formatExports: readonly string[];
  readonly uses: SinkUse[] = [];

  constructor(
    program: ts.Program,
    private readonly roles: FormatRoles,
  ) {
    this.checker = program.getTypeChecker();
    this.sources = program
      .getSourceFiles()
      .filter((file) => !file.isDeclarationFile && isProductSource(file.fileName));
    const formatSource = program.getSourceFile(FORMAT_MODULE);
    const moduleSymbol =
      formatSource === undefined ? undefined : this.checker.getSymbolAtLocation(formatSource);
    if (moduleSymbol === undefined) {
      throw new Error("src/lib/format/index.ts is not part of the program");
    }
    const exported = this.checker.getExportsOfModule(moduleSymbol);
    this.formatExports = exported
      .filter((symbol) => (symbol.flags & ts.SymbolFlags.Function) !== 0)
      .map((symbol) => symbol.name)
      .sort();
    const named = new Map(exported.map((symbol) => [symbol.name, symbol]));
    const symbolOf = (name: string): ts.Symbol => {
      const symbol = named.get(name);
      if (symbol === undefined) {
        throw new Error(`src/lib/format does not export ${name}`);
      }
      return symbol;
    };
    for (const name of roles.dateSinks) {
      this.sinks.set(symbolOf(name), { name, wants: "date" });
    }
    for (const name of roles.instantSinks) {
      this.sinks.set(symbolOf(name), { name, wants: "date-time" });
    }
    for (const name of roles.dateProducers) {
      this.producers.set(symbolOf(name), { name, format: "date" });
    }
    for (const name of roles.instantProducers) {
      this.producers.set(symbolOf(name), { name, format: "date-time" });
    }
    for (const [name, member] of Object.entries(roles.dateOptions)) {
      this.optionSinks.set(symbolOf(name), { name, member });
    }
  }

  run(): void {
    for (const file of this.sources) {
      this.index(file);
    }
    for (const file of this.sources) {
      const path = relative(FRONTEND, file.fileName);
      // The format module implements the sinks; trusted files own their dates (a date picker).
      if (file.fileName !== FORMAT_MODULE && !this.roles.trusted.includes(path)) {
        this.visit(file);
      }
    }
    this.uses.sort((a, b) => a.file.localeCompare(b.file) || a.line - b.line);
  }

  // ---- indexes ---------------------------------------------------------------------------------

  private push<Key>(map: Map<Key, ts.Expression[]>, key: Key, value: ts.Expression): void {
    const list = map.get(key);
    if (list === undefined) {
      map.set(key, [value]);
    } else {
      list.push(value);
    }
  }

  /** The symbol a name refers to, through import aliases and local export pairs. */
  private symbolAt(node: ts.Node): ts.Symbol | undefined {
    const symbol = this.checker.getSymbolAtLocation(node);
    if (symbol === undefined) {
      return undefined;
    }
    const target =
      (symbol.flags & ts.SymbolFlags.Alias) !== 0 ? this.checker.getAliasedSymbol(symbol) : symbol;
    return this.checker.getExportSymbolOfSymbol(target);
  }

  /** What is assigned to each declared member, passed for each parameter and to each callee. */
  private index(node: ts.Node): void {
    if (ts.isJsxAttribute(node) && node.initializer !== undefined) {
      const contextual = this.checker.getContextualType(node.parent);
      const member =
        contextual === undefined
          ? undefined
          : this.checker.getPropertyOfType(contextual, node.name.getText());
      const value = ts.isJsxExpression(node.initializer)
        ? node.initializer.expression
        : node.initializer;
      for (const declaration of member?.declarations ?? []) {
        if (value !== undefined) {
          this.push(this.assigned, declaration, value);
        }
      }
    } else if (
      (ts.isPropertyAssignment(node) || ts.isShorthandPropertyAssignment(node)) &&
      ts.isObjectLiteralExpression(node.parent)
    ) {
      const contextual = this.checker.getContextualType(node.parent);
      const member =
        contextual === undefined
          ? undefined
          : this.checker.getPropertyOfType(contextual, memberName(node.name));
      const value = ts.isPropertyAssignment(node) ? node.initializer : node.name;
      for (const declaration of member?.declarations ?? []) {
        if (declaration !== node) {
          this.push(this.assigned, declaration, value);
        }
      }
    } else if (ts.isCallExpression(node)) {
      const declaration = this.checker.getResolvedSignature(node)?.declaration;
      if (declaration !== undefined && !ts.isJSDocSignature(declaration)) {
        node.arguments.forEach((argument, position) => {
          const parameter = declaration.parameters[position];
          if (parameter !== undefined) {
            this.push(this.passed, parameter, argument);
          }
        });
      }
      const [first] = node.arguments;
      const callee = ts.isIdentifier(node.expression) ? this.symbolAt(node.expression) : undefined;
      if (callee !== undefined && first !== undefined) {
        this.push(this.calls, callee, first);
      }
    } else if (
      ts.isBinaryExpression(node) &&
      node.operatorToken.kind === ts.SyntaxKind.EqualsToken &&
      ts.isIdentifier(node.left)
    ) {
      const symbol = this.symbolAt(node.left);
      if (symbol !== undefined) {
        this.push(this.reassigned, symbol, node.right);
      }
    }
    // A function value used other than as a callee (passed as a callback) may be called anywhere,
    // except as the date callback of a date component, which calls it with a business date.
    if (
      ts.isIdentifier(node) &&
      !(ts.isCallExpression(node.parent) && node.parent.expression === node) &&
      !ts.isBindingElement(node.parent)
    ) {
      const symbol = this.symbolAt(node);
      if (symbol !== undefined) {
        (this.isDateCallback(node) ? this.dateSetters : this.escaped).add(symbol);
      }
    }
    ts.forEachChild(node, (child) => {
      this.index(child);
    });
  }

  /** `<DateInput onValue={setDate} />`: the identifier is the value of a date callback prop. */
  private isDateCallback(node: ts.Identifier): boolean {
    const attribute = ts.isJsxExpression(node.parent) ? node.parent.parent : undefined;
    if (attribute === undefined || !ts.isJsxAttribute(attribute)) {
      return false;
    }
    const element = attribute.parent.parent;
    return this.roles.dateCallbacks[element.tagName.getText()] === attribute.name.getText();
  }

  // ---- sinks -----------------------------------------------------------------------------------

  private record(node: ts.Node, sink: string, wants: DateFormat, value: ts.Expression): void {
    let argument = value;
    while (ts.isParenthesizedExpression(argument)) {
      argument = argument.expression;
    }
    const flows = this.flows(argument, { depth: 0, active: new Set() });
    const origins = flows.map(
      (flow) =>
        flow.origin ?? {
          kind: "untraced" as const,
          text: `${ts.SyntaxKind[flow.node.kind]} ${brief(flow.node)}`,
        },
    );
    const unique = new Map(origins.map((origin) => [`${origin.kind}|${origin.text}`, origin]));
    const source = node.getSourceFile();
    this.uses.push({
      file: relative(FRONTEND, source.fileName),
      line: source.getLineAndCharacterOfPosition(node.getStart()).line + 1,
      sink,
      argument: argument.getText().replace(/\s+/g, " "),
      wants,
      origins: [...unique.values()],
    });
  }

  private visit(node: ts.Node): void {
    if (ts.isCallExpression(node)) {
      const callee = this.symbolAt(node.expression);
      const sink = callee === undefined ? undefined : this.sinks.get(callee);
      const [first, second] = node.arguments;
      if (sink !== undefined && first !== undefined) {
        this.record(node, sink.name, sink.wants, first);
      }
      const option = callee === undefined ? undefined : this.optionSinks.get(callee);
      if (option !== undefined && second !== undefined) {
        const name = `${option.name} ${option.member}`;
        const member = ts.isObjectLiteralExpression(second)
          ? second.properties.find(
              (property) =>
                (ts.isPropertyAssignment(property) || ts.isShorthandPropertyAssignment(property)) &&
                memberName(property.name) === option.member,
            )
          : undefined;
        if (member !== undefined && ts.isPropertyAssignment(member)) {
          this.record(node, name, "date", member.initializer);
        } else if (member !== undefined && ts.isShorthandPropertyAssignment(member)) {
          this.record(node, name, "date", member.name);
        } else if (!ts.isObjectLiteralExpression(second)) {
          this.record(node, name, "date", second);
        }
      }
    }
    if (ts.isObjectLiteralExpression(node)) {
      this.visitColumn(node);
      this.visitApiObject(node);
    }
    ts.forEachChild(node, (child) => {
      this.visit(child);
    });
  }

  /** A `GridColumn` of kind `date` or `timestamp`: its `value` reaches the default renderer and Mod C. */
  private visitColumn(node: ts.ObjectLiteralExpression): void {
    const contextual = this.checker.getContextualType(node);
    const typeName = (contextual?.aliasSymbol ?? contextual?.symbol)?.name;
    if (typeName !== "GridColumn") {
      return;
    }
    const members = new Map<string, ts.Expression>();
    for (const property of node.properties) {
      if (ts.isPropertyAssignment(property)) {
        members.set(memberName(property.name), property.initializer);
      }
    }
    const kind = members.get("kind");
    const value = members.get("value");
    if (kind === undefined || value === undefined) {
      return;
    }
    const kinds = kindsOf(this.checker.getTypeAtLocation(kind));
    for (const [literal, wants] of [
      ["date", "date"],
      ["timestamp", "date-time"],
    ] as const) {
      if (kinds.includes(literal)) {
        for (const result of returnsOf(value)) {
          this.record(node, `column kind "${literal}"`, wants, result);
        }
      }
    }
  }

  /** An object literal typed by an API schema: its `date` and `date-time` members (a request body). */
  private visitApiObject(node: ts.ObjectLiteralExpression): void {
    const contextual = this.checker.getContextualType(node);
    if (contextual === undefined) {
      return;
    }
    for (const property of node.properties) {
      if (!ts.isPropertyAssignment(property) && !ts.isShorthandPropertyAssignment(property)) {
        continue;
      }
      const name = memberName(property.name);
      const parts = contextual.isUnion() ? contextual.types : [contextual];
      const declarations = parts.flatMap(
        (part) => this.checker.getPropertyOfType(part, name)?.declarations ?? [],
      );
      const found = declarations
        .filter((declaration) => declaration.getSourceFile().fileName === SCHEMA_FILE)
        .map((declaration) => this.formats.ofDeclaration(declarationPath(declaration)));
      const formats = new Set(found.flatMap((item) => item.formats));
      const [label] = found.map((item) => item.label);
      const wants = formats.has("date-time") ? "date-time" : formats.has("date") ? "date" : null;
      if (
        label === undefined ||
        wants === null ||
        (formats.has("date") && formats.has("date-time"))
      ) {
        continue;
      }
      const value = ts.isPropertyAssignment(property) ? property.initializer : property.name;
      this.record(property, `member ${label}`, wants, value);
    }
  }

  // ---- flows -----------------------------------------------------------------------------------

  private known(node: ts.Node, origin: Origin): Flow[] {
    return [{ node, element: false, origin }];
  }

  private untraced(node: ts.Node, text: string): Flow[] {
    return this.known(node, { kind: "untraced", text });
  }

  private all(expressions: readonly ts.Expression[], trace: Trace): Flow[] {
    return expressions.flatMap((expression) => this.flows(expression, trace));
  }

  /** The values that can reach `expression`, each traced back as far as the rules above go. */
  private flows(expression: ts.Expression, trace: Trace): Flow[] {
    if (trace.depth > MAX_DEPTH) {
      return this.untraced(expression, "too deep to follow");
    }
    if (trace.active.has(expression)) {
      return [];
    }
    trace.active.add(expression);
    try {
      return this.step(expression, { depth: trace.depth + 1, active: trace.active });
    } finally {
      trace.active.delete(expression);
    }
  }

  private step(expression: ts.Expression, trace: Trace): Flow[] {
    if (
      ts.isParenthesizedExpression(expression) ||
      ts.isNonNullExpression(expression) ||
      ts.isAsExpression(expression) ||
      ts.isSatisfiesExpression(expression)
    ) {
      return this.flows(expression.expression, trace);
    }
    if (ts.isConditionalExpression(expression)) {
      return this.all([expression.whenTrue, expression.whenFalse], trace);
    }
    if (ts.isBinaryExpression(expression)) {
      const operator = expression.operatorToken.kind;
      if (
        operator === ts.SyntaxKind.QuestionQuestionToken ||
        operator === ts.SyntaxKind.BarBarToken
      ) {
        return this.all([expression.left, expression.right], trace);
      }
      if (operator === ts.SyntaxKind.AmpersandAmpersandToken) {
        return this.flows(expression.right, trace);
      }
    }
    if (ts.isStringLiteral(expression) || ts.isNoSubstitutionTemplateLiteral(expression)) {
      return this.known(expression, { kind: "constant", text: JSON.stringify(expression.text) });
    }
    if (
      expression.kind === ts.SyntaxKind.NullKeyword ||
      (ts.isIdentifier(expression) && expression.text === "undefined")
    ) {
      return this.known(expression, { kind: "constant", text: expression.getText() });
    }
    if (ts.isPropertyAccessExpression(expression)) {
      return this.member(
        expression,
        this.flows(expression.expression, trace),
        expression.name.text,
        trace,
      );
    }
    if (ts.isElementAccessExpression(expression)) {
      const key = expression.argumentExpression;
      if (ts.isStringLiteral(key)) {
        return this.member(expression, this.flows(expression.expression, trace), key.text, trace);
      }
      const holder = this.checker.getNonNullableType(
        this.checker.getTypeAtLocation(expression.expression),
      );
      // `dates[0]`, `rows[index]`: an element of the array. A computed key of a record is free-form.
      return this.checker.isArrayLikeType(holder)
        ? this.elements(this.flows(expression.expression, trace))
        : this.untraced(expression, `free-form member ${brief(expression)}`);
    }
    if (ts.isCallExpression(expression)) {
      return this.call(expression, trace);
    }
    if (ts.isIdentifier(expression)) {
      const declarations = this.symbolAt(expression)?.declarations ?? [];
      return declarations.length === 0
        ? [{ node: expression, element: false }]
        : declarations.flatMap((declaration) => this.binding(expression, declaration, trace));
    }
    // An object or array literal, a template, `await`: typed, and not a value this trace knows.
    return [{ node: expression, element: false }];
  }

  /** The elements of arrays: an array whose origin is known gives its elements that origin. */
  private elements(flows: readonly Flow[]): Flow[] {
    return flows.map((flow) => ({ ...flow, element: true }));
  }

  /** The type of the value a flow stands for. */
  private typeOf(flow: Flow): ts.Type {
    const type = this.checker.getNonNullableType(this.checker.getTypeAtLocation(flow.node));
    if (!flow.element) {
      return type;
    }
    const parts = type.isUnion() ? type.types : [type];
    const elements = parts.flatMap((part) => {
      const element = this.checker.getIndexTypeOfType(part, ts.IndexKind.Number);
      return element === undefined ? [] : [this.checker.getNonNullableType(element)];
    });
    return elements[0] ?? type;
  }

  /** The declarations of member `name` on the types of `owners` (every part of a union). */
  private memberDeclarations(owners: readonly Flow[], name: string): Set<ts.Declaration> | null {
    const found = new Set<ts.Declaration>();
    for (const owner of owners) {
      const type = this.typeOf(owner);
      for (const part of type.isUnion() ? type.types : [type]) {
        const member = this.checker.getPropertyOfType(this.checker.getApparentType(part), name);
        for (const declaration of member?.declarations ?? []) {
          if (ts.isIndexSignatureDeclaration(declaration)) {
            return null;
          }
          found.add(declaration);
        }
      }
    }
    return found.size === 0 ? null : found;
  }

  /** Member `name` of the values in `owners`; `access` is the expression that reads it. */
  private member(access: ts.Node, owners: readonly Flow[], name: string, trace: Trace): Flow[] {
    const typed = owners.length === 0 ? [{ node: access, element: false }] : owners;
    const declarations =
      owners.length === 0
        ? new Set(this.checker.getSymbolAtLocation(access)?.declarations ?? [])
        : this.memberDeclarations(typed, name);
    if (declarations === null || declarations.size === 0) {
      return this.untraced(access, `free-form member ${brief(access)}`);
    }
    return [...declarations].flatMap((declaration) =>
      this.declared(access, declaration, name, trace),
    );
  }

  /** A member from its declaration: an API property, an object literal member or a local type. */
  private declared(
    access: ts.Node,
    declaration: ts.Declaration,
    name: string,
    trace: Trace,
  ): Flow[] {
    const source = declaration.getSourceFile();
    if (source.fileName === SCHEMA_FILE) {
      const { label, formats } = this.formats.ofDeclaration(declarationPath(declaration));
      return formats.length === 0
        ? this.untraced(access, `API member ${label} without a format in the OpenAPI document`)
        : formats.flatMap((format) => this.known(access, { kind: "field", text: label, format }));
    }
    if (ts.isPropertyAssignment(declaration)) {
      return this.flows(declaration.initializer, trace);
    }
    if (ts.isShorthandPropertyAssignment(declaration)) {
      return this.flows(declaration.name, trace);
    }
    if (ts.isBindingElement(declaration) || ts.isParameter(declaration)) {
      return this.binding(access, declaration, trace);
    }
    if (!ts.isPropertySignature(declaration) && !ts.isPropertyDeclaration(declaration)) {
      return this.untraced(access, `member ${name} declared as ${ts.SyntaxKind[declaration.kind]}`);
    }
    if (source.fileName === FORMAT_MODULE && this.isDateResult(declaration)) {
      return this.known(access, {
        kind: "produced",
        text: `${name} of a parsed date`,
        format: "date",
      });
    }
    if (!isProductSource(source.fileName)) {
      return this.untraced(access, `member ${name} of a library type`);
    }
    const values = this.assigned.get(declaration) ?? [];
    const found = this.all(values, trace);
    // A hand-written mirror of an API shape: its values come from the API, so its name decides.
    if (values.length === 0 || source.fileName.startsWith(`${MIRROR_DIR}/`)) {
      const format = this.formats.ofName(name);
      found.push(
        ...(format === null
          ? this.untraced(access, `member ${name}: no value assigned and no single API format`)
          : this.known(access, { kind: "field", text: `${name} (by name)`, format })),
      );
    }
    return found;
  }

  private isDateResult(declaration: ts.Declaration): boolean {
    let current: ts.Node = declaration;
    while (!ts.isSourceFile(current)) {
      if (ts.isTypeAliasDeclaration(current)) {
        return (
          this.roles.dateResults.includes(current.name.text) &&
          ts.isPropertySignature(declaration) &&
          memberName(declaration.name) === "value"
        );
      }
      current = current.parent;
    }
    return false;
  }

  private call(expression: ts.CallExpression, trace: Trace): Flow[] {
    const callee = this.symbolAt(expression.expression);
    const producer = callee === undefined ? undefined : this.producers.get(callee);
    if (producer !== undefined) {
      return this.known(expression, {
        kind: "produced",
        text: producer.name,
        format: producer.format,
      });
    }
    if (ts.isPropertyAccessExpression(expression.expression)) {
      const receiver = expression.expression.expression;
      const method = expression.expression.name.text;
      const holder = this.checker.getNonNullableType(this.checker.getTypeAtLocation(receiver));
      const [callback] = expression.arguments;
      if (method === "get" && this.checker.typeToString(holder) === "URLSearchParams") {
        return this.known(expression, {
          kind: "client",
          text: `URL parameter ${brief(expression)}`,
        });
      }
      if (this.checker.isArrayLikeType(holder)) {
        if ((method === "map" || method === "flatMap") && callback !== undefined) {
          return this.elements(this.all(returnsOf(callback), trace));
        }
        if (SAME_ELEMENTS.has(method)) {
          return this.flows(receiver, trace);
        }
        if (ONE_ELEMENT.has(method)) {
          return this.elements(this.flows(receiver, trace));
        }
        if (REDUCERS.has(method) && callback !== undefined) {
          // What the callback returns, and the initial value.
          return this.all([...returnsOf(callback), ...expression.arguments.slice(1)], trace);
        }
      }
    }
    const declaration = this.checker.getResolvedSignature(expression)?.declaration;
    if (
      declaration !== undefined &&
      !ts.isJSDocSignature(declaration) &&
      isProductSource(declaration.getSourceFile().fileName)
    ) {
      const results = returnsOf(declaration);
      if (results.length > 0) {
        return this.all(results, trace);
      }
    }
    return this.untraced(expression, `call ${brief(expression)}`);
  }

  /** The values bound to a name by its declaration. */
  private binding(use: ts.Node, declaration: ts.Declaration, trace: Trace): Flow[] {
    if (ts.isVariableDeclaration(declaration) && ts.isIdentifier(declaration.name)) {
      // Its initializer and, for a `let`, every `name = value` assignment.
      const symbol = this.symbolAt(declaration.name);
      const values = [
        ...(declaration.initializer === undefined ? [] : [declaration.initializer]),
        ...(symbol === undefined ? [] : (this.reassigned.get(symbol) ?? [])),
      ];
      return values.length === 0
        ? this.untraced(use, `variable ${declaration.name.text} without a value`)
        : this.all(values, trace);
    }
    if (ts.isBindingElement(declaration)) {
      return ts.isArrayBindingPattern(declaration.parent)
        ? this.state(use, declaration, declaration.parent, trace)
        : this.destructured(use, declaration, declaration.parent, trace);
    }
    if (ts.isParameter(declaration)) {
      return this.parameter(use, declaration, trace);
    }
    if (ts.isShorthandPropertyAssignment(declaration)) {
      const value = this.checker.getShorthandAssignmentValueSymbol(declaration);
      return (value?.declarations ?? []).flatMap((target) => this.binding(use, target, trace));
    }
    // A function, class, enum or import without a value this trace follows.
    return [{ node: use, element: false }];
  }

  /** `const { name } = owner` or a destructured parameter: member `name` of what is destructured. */
  private destructured(
    use: ts.Node,
    element: ts.BindingElement,
    pattern: ts.ObjectBindingPattern,
    trace: Trace,
  ): Flow[] {
    const name = memberName(element.propertyName ?? element.name);
    const holder = pattern.parent;
    let owners: Flow[] = [];
    if (ts.isVariableDeclaration(holder) && holder.initializer !== undefined) {
      owners = this.flows(holder.initializer, trace);
    } else if (ts.isParameter(holder)) {
      owners = this.parameter(pattern, holder, trace).filter((flow) => flow.node !== pattern);
    } else if (ts.isBindingElement(holder)) {
      owners = this.binding(pattern, holder, trace).filter((flow) => flow.node !== pattern);
    }
    if (owners.length > 0) {
      return this.member(use, owners, name, trace);
    }
    // No value to follow (a component's props): the members of the annotated type.
    const type = this.checker.getNonNullableType(this.checker.getTypeAtLocation(pattern));
    const declarations = new Set(
      (type.isUnion() ? type.types : [type]).flatMap(
        (part) => this.checker.getPropertyOfType(part, name)?.declarations ?? [],
      ),
    );
    return declarations.size === 0
      ? this.untraced(use, `destructured member ${name}`)
      : [...declarations].flatMap((declaration) => this.declared(use, declaration, name, trace));
  }

  /** `const [value, setValue] = useState(initial)`: the initial value and every `setValue(x)`. */
  private state(
    use: ts.Node,
    element: ts.BindingElement,
    pattern: ts.ArrayBindingPattern,
    trace: Trace,
  ): Flow[] {
    const holder = pattern.parent;
    const [value, setter] = pattern.elements;
    if (
      !ts.isVariableDeclaration(holder) ||
      holder.initializer === undefined ||
      !ts.isCallExpression(holder.initializer) ||
      !/(^|\.)useState$/.test(holder.initializer.expression.getText()) ||
      element !== value
    ) {
      return this.untraced(use, `array binding ${brief(element)}`);
    }
    const found: Flow[] = [];
    const [initial] = holder.initializer.arguments;
    if (initial !== undefined) {
      const lazy = ts.isArrowFunction(initial) || ts.isFunctionExpression(initial);
      found.push(...this.all(lazy ? returnsOf(initial) : [initial], trace));
    }
    if (setter !== undefined && ts.isBindingElement(setter) && ts.isIdentifier(setter.name)) {
      const symbol = this.symbolAt(setter.name);
      const name = setter.name.text;
      found.push(...this.all(symbol === undefined ? [] : (this.calls.get(symbol) ?? []), trace));
      if (symbol !== undefined && this.dateSetters.has(symbol)) {
        found.push(
          ...this.known(use, {
            kind: "produced",
            text: `${name} as a date callback`,
            format: "date",
          }),
        );
      }
      if (symbol !== undefined && this.escaped.has(symbol)) {
        found.push(...this.untraced(use, `state set through the callback ${name}`));
      }
    }
    return found;
  }

  private parameter(use: ts.Node, parameter: ts.ParameterDeclaration, trace: Trace): Flow[] {
    const owner = parameter.parent;
    const position = owner.parameters.indexOf(parameter);
    if (
      (ts.isArrowFunction(owner) || ts.isFunctionExpression(owner)) &&
      ts.isCallExpression(owner.parent) &&
      ts.isPropertyAccessExpression(owner.parent.expression) &&
      owner.parent.arguments[0] === owner
    ) {
      const method = owner.parent.expression.name.text;
      const receiver = owner.parent.expression.expression;
      const reducer = REDUCERS.has(method);
      if (reducer && position === 0) {
        // The accumulated value: what the reduction itself yields.
        return this.flows(owner.parent, trace);
      }
      if (reducer || ELEMENT_CALLBACKS.has(method)) {
        // The element parameter of an array callback is an element of the array.
        return position === (reducer ? 1 : 0)
          ? this.elements(this.flows(receiver, trace))
          : this.untraced(use, `parameter ${brief(parameter.name)} of an array callback`);
      }
    }
    const values = this.passed.get(parameter) ?? [];
    // Without a call site (a component's props, a callback a library calls): the annotated type.
    return values.length === 0 ? [{ node: use, element: false }] : this.all(values, trace);
  }
}

function memberName(name: ts.Node): string {
  return ts.isIdentifier(name) || ts.isStringLiteral(name) || ts.isNumericLiteral(name)
    ? name.text
    : name.getText();
}

function brief(node: ts.Node): string {
  const text = node.getText().replace(/\s+/g, " ");
  return text.length > 60 ? `${text.slice(0, 57)}...` : text;
}

/** The names from the `components` or `operations` interface of `schema.d.ts` down to a member. */
function declarationPath(node: ts.Node): string[] {
  const names: string[] = [];
  let current: ts.Node = node;
  while (!ts.isSourceFile(current)) {
    if (ts.isPropertySignature(current)) {
      names.unshift(memberName(current.name));
    } else if (ts.isInterfaceDeclaration(current)) {
      names.unshift(current.name.text);
      break;
    }
    current = current.parent;
  }
  return names;
}

/** The string literals a `kind` expression can be. */
function kindsOf(type: ts.Type): string[] {
  const parts = type.isUnion() ? type.types : [type];
  return parts.flatMap((part) => (part.isStringLiteral() ? [part.value] : []));
}

/** The expressions a function-like node returns (not those of nested functions). */
function returnsOf(node: ts.Node): ts.Expression[] {
  if (!ts.isFunctionLike(node) || !("body" in node) || node.body === undefined) {
    return [];
  }
  const body: ts.Node = node.body;
  if (!ts.isBlock(body)) {
    return [body as ts.Expression];
  }
  const found: ts.Expression[] = [];
  const walk = (child: ts.Node): void => {
    if (ts.isFunctionLike(child)) {
      return;
    }
    if (ts.isReturnStatement(child) && child.expression !== undefined) {
      found.push(child.expression);
    }
    ts.forEachChild(child, walk);
  };
  ts.forEachChild(body, walk);
  return found;
}

/**
 * Every use of a date or instant function of the format module in the product sources, with the
 * origins of its argument. `overlay` adds source files (path from `frontend/` → text) to the program.
 */
export function traceDateFlow(
  roles: FormatRoles,
  overlay: Readonly<Record<string, string>> = {},
): DateFlow {
  const files = new Map(
    Object.entries(overlay).map(([path, text]) => [resolve(FRONTEND, path), text]),
  );
  const tracer = new Tracer(createProgram(files), roles);
  tracer.run();
  return { formatExports: tracer.formatExports, uses: tracer.uses };
}

/** `field` and `produced` origins whose format is not the one the sink wants. */
export function mismatches(use: SinkUse): Origin[] {
  return use.origins.filter(
    (origin) =>
      (origin.kind === "field" || origin.kind === "produced") && origin.format !== use.wants,
  );
}

/** Origins the trace could not follow; a use without any origin counts as untraced. */
export function untraced(use: SinkUse): Origin[] {
  const found = use.origins.filter((origin) => origin.kind === "untraced");
  return use.origins.length === 0 ? [{ kind: "untraced", text: "no origin found" }] : found;
}
