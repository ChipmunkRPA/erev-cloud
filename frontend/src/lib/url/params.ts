// Canonical URL parameters (SCREENS §0.5 SCR-URL-20; docs/dev-guide.md DG-FE-03). Pairs are kept
// raw, so percent-encoded commas inside `f.*` values survive canonicalisation.
export const CANONICAL_ORDER = [
  "entity",
  "period",
  "book",
  "currency_view",
  "known_at",
  "snapshot",
  "run",
  "p.*",
  "layout",
  "rows",
  "granularity",
  "measure",
  "format",
  "from",
  "to",
  "run.*",
  "calendar",
  "rate_set",
  "version",
  "template",
  "mode",
  "event_set",
  "action",
  "kind",
  "obligation",
  "step",
  "reason",
  "next",
  "view",
  "q",
  "sort",
  "f.*",
  "pane",
  "explain",
  "drawer",
  "row",
  "sheet",
  "source_record",
  "node",
  "event",
  "dialog",
  "tour",
  "panel",
] as const;

export type ParamName = (typeof CANONICAL_ORDER)[number];

export interface CanonicaliseOptions {
  /** Parameters the screen uses; `p.*`, `run.*` and `f.*` admit their families. Default: all. */
  readonly declared?: readonly ParamName[];
  /** Filter fields in column order; fields not listed follow in link order. */
  readonly filterColumns?: readonly string[];
  /** Values for missing parameters, for example the BR-UX-01 context defaults. */
  readonly defaults?: Readonly<Partial<Record<ParamName, string>>>;
}

const ORDER: readonly string[] = CANONICAL_ORDER;

function family(name: string): string | null {
  if (ORDER.includes(name)) {
    return name;
  }
  const dot = name.indexOf(".");
  const prefixed = dot > 0 ? `${name.slice(0, dot)}.*` : "";
  return ORDER.includes(prefixed) ? prefixed : null;
}

function decodeName(raw: string): string {
  try {
    return decodeURIComponent(raw.replace(/\+/g, " "));
  } catch {
    return raw;
  }
}

interface Pair {
  readonly raw: string;
  readonly name: string;
  readonly slot: number;
  readonly column: number;
  readonly position: number;
}

export interface RawParam {
  /** The decoded parameter name. */
  readonly name: string;
  /** The value as written in the link, still percent-encoded. */
  readonly value: string;
  readonly raw: string;
}

/** The pairs of a search string in link order, with decoded names and raw values. */
export function rawParams(search: string): readonly RawParam[] {
  const body = search.startsWith("?") ? search.slice(1) : search;
  return body
    .split("&")
    .filter((raw) => raw !== "")
    .map((raw) => {
      const equals = raw.indexOf("=");
      return {
        name: decodeName(equals < 0 ? raw : raw.slice(0, equals)),
        value: equals < 0 ? "" : raw.slice(equals + 1),
        raw,
      };
    });
}

/** Decodes one raw value; an undecodable value is kept as written. */
export function decodeValue(raw: string): string {
  return decodeName(raw);
}

/**
 * Replaces parameters by name with raw values (null removes them) after removing every parameter
 * whose name starts with one of `clearPrefixes`. Parameters of the SCR-URL-20 order are sorted into
 * it; others keep their link order at the end.
 */
export function withParams(
  search: string,
  changes: Readonly<Record<string, string | null>>,
  clearPrefixes: readonly string[] = [],
): string {
  const kept = rawParams(search)
    .filter(
      (param) =>
        !(param.name in changes) && !clearPrefixes.some((prefix) => param.name.startsWith(prefix)),
    )
    .map((param) => ({ name: param.name, raw: param.raw }));
  for (const [name, value] of Object.entries(changes)) {
    if (value !== null) {
      kept.push({ name, raw: `${encodeURIComponent(name)}=${value}` });
    }
  }
  const slot = (name: string) => {
    const known = family(name);
    return known === null ? ORDER.length : ORDER.indexOf(known);
  };
  const ordered = kept
    .map((param, position) => ({ ...param, position }))
    .sort((a, b) => slot(a.name) - slot(b.name) || a.position - b.position);
  return ordered.length === 0 ? "" : `?${ordered.map((param) => param.raw).join("&")}`;
}

/** Orders a search string per SCR-URL-20 and removes parameters the screen does not declare. */
export function canonicalise(search: string, options: CanonicaliseOptions = {}): string {
  const declared = new Set<string>(options.declared ?? CANONICAL_ORDER);
  const columns = options.filterColumns ?? [];
  const pairs: Pair[] = [];
  const body = search.startsWith("?") ? search.slice(1) : search;
  const add = (raw: string, name: string, position: number): void => {
    const slot = family(name);
    if (slot === null || !declared.has(slot)) {
      return;
    }
    const column = slot === "f.*" ? columns.indexOf(name.slice(2)) : -1;
    pairs.push({
      raw,
      name,
      slot: ORDER.indexOf(slot),
      column: column < 0 ? columns.length : column,
      position,
    });
  };
  body.split("&").forEach((raw, position) => {
    if (raw !== "") {
      add(raw, decodeName(raw.split("=", 1)[0] ?? ""), position);
    }
  });
  const present = new Set(pairs.map((pair) => pair.name));
  for (const [name, value] of Object.entries(options.defaults ?? {})) {
    if (value !== undefined && !present.has(name)) {
      add(
        `${encodeURIComponent(name)}=${encodeURIComponent(value)}`,
        name,
        Number.MAX_SAFE_INTEGER,
      );
    }
  }
  pairs.sort((a, b) => a.slot - b.slot || a.column - b.column || a.position - b.position);
  return pairs.length === 0 ? "" : `?${pairs.map((pair) => pair.raw).join("&")}`;
}
