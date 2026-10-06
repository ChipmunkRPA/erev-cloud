// Lists (04 API-C-09; docs/dev-guide.md DG-LST-01 to DG-LST-06, DG-FE-07). Keyset pages of
// `{items, next_cursor}`; a repeated parameter means IN; `count=true` adds `X-Erev-Total-Count`, capped
// as `100000+`. The DataGrid asks for the count on the first page only.
import { send } from "./client";
import { readProblem } from "./problems";

export const GRID_PAGE_SIZE = 200;
export const TOTAL_COUNT_HEADER = "X-Erev-Total-Count";

export type ListQueryValue = string | number | boolean | readonly string[] | null | undefined;
export type ListQuery = Readonly<Record<string, ListQueryValue>>;

export interface ListTotal {
  readonly count: number;
  /** True for the `100000+` cap. */
  readonly capped: boolean;
}

export interface ListPage<T> {
  readonly items: readonly T[];
  readonly nextCursor: string | null;
  readonly total: ListTotal | null;
}

export interface ListPageOptions {
  readonly limit?: number;
  /** Ask for the total count; the default asks on the first page only. */
  readonly count?: boolean;
}

/** The search string of a list query: arrays repeat their parameter; null and undefined are omitted. */
export function listSearch(query: ListQuery): string {
  const params = new URLSearchParams();
  for (const [name, value] of Object.entries(query)) {
    if (value === null || value === undefined) {
      continue;
    }
    if (Array.isArray(value)) {
      for (const item of value as readonly string[]) {
        params.append(name, item);
      }
    } else {
      params.append(name, String(value));
    }
  }
  const text = params.toString();
  return text === "" ? "" : `?${text}`;
}

export function parseTotalCount(header: string | null): ListTotal | null {
  const match = header === null ? null : /^(\d+)(\+)?$/.exec(header.trim());
  if (match === null) {
    return null;
  }
  return { count: Number(match[1]), capped: match[2] === "+" };
}

/** Fetches one page of a list route, or throws its `ApiProblem`. */
export async function fetchListPage<T>(
  path: string,
  query: ListQuery,
  cursor: string | null,
  options: ListPageOptions = {},
): Promise<ListPage<T>> {
  const search = listSearch({
    ...query,
    limit: options.limit ?? GRID_PAGE_SIZE,
    cursor,
    count: (options.count ?? cursor === null) ? true : undefined,
  });
  const response = await send("GET", `${path}${search}`);
  if (!response.ok) {
    throw await readProblem(response);
  }
  const body = (await response.json()) as {
    readonly items: readonly T[];
    readonly next_cursor: string | null;
  };
  return {
    items: body.items,
    nextCursor: body.next_cursor,
    total: parseTotalCount(response.headers.get(TOTAL_COUNT_HEADER)),
  };
}
