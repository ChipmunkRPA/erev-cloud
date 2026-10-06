// SF-24:results Search results (SCREENS §1.4, §0.4 RT-95 `/search?q=<query>&f.scope=is:<scope>`; 04
// API-R-55 `GET /search`, §16.13 API-S-SearchResult; DESIGN_SYSTEM DS-CMP-10 static variant, DS-CMP-13;
// BUILD_SPEC CTR-28). `h1` "Search results for "<query>"", a FilterBar with the quick search `q` and
// the chip field "Scope", and one static table a scope that found something, in E-120 order, each
// with the columns of SCREENS §1.4 and at most 25 rows; "Show more <scope>" reads the next 25 by the
// scope's cursor. A record opens the route §1.4 builds from its scope and id; an obligation's needs
// its contract, read from `GET /obligations/{id}` for the rows shown. The route asks `contract.read`
// for any entity (04 API-R-55) and shows the access-limited screen without it. A text the route
// would refuse — shorter than two characters, or without a letter or digit — is not sent.
import { useInfiniteQuery, useQueries, useQuery } from "@tanstack/react-query";
import { type ReactNode, useMemo } from "react";
import { Link, useLocation } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { Skeleton } from "../../components/feedback/Skeleton";
import { FilterBar } from "../../components/filter-bar/FilterBar";
import { type FilterField, parseFilters } from "../../components/filter-bar/filters";
import { Button } from "../../components/ui/Button";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { ApiProblem } from "../../lib/api/problems";
import { useMe } from "../../lib/api/queries/me";
import {
  fetchObligationContract,
  fetchSearch,
  fetchSearchScope,
  isSearchScope,
  obligationContractKey,
  obligationRoute,
  RECORD_ROUTE_PATTERNS,
  recordRoute,
  RESULTS_LIMIT,
  SEARCH_PERMISSION,
  SEARCH_SCOPES,
  SEARCH_STATUS_ENUM,
  searchable,
  type SearchGroup,
  type SearchItem,
  searchKey,
  type SearchScope,
} from "../../lib/api/queries/search";
import { queryKey } from "../../lib/api/query-keys";
import { t } from "../../lib/i18n/t";
import { useBuiltPaths } from "../settings/index";

/** SCREENS §0.5: the chip field of the page, `f.scope=is:<scope>`. */
export const SCOPE_FIELD = "scope";

const HEAD = "px-2 py-1.5 text-start font-medium";
const CELL = "px-2 py-1.5";
const MONO = "font-mono text-mono-sm text-fg-1";
const MONO_LINK = `${MONO} underline decoration-dotted underline-offset-4 hover:decoration-solid`;

function scopeLabel(scope: SearchScope): string {
  return t(`search.scope.${scope}`);
}

function LoadError({
  title,
  problem,
  onRetry,
}: {
  readonly title: string;
  readonly problem: unknown;
  readonly onRetry: () => void;
}) {
  return (
    <Banner
      tone="negative"
      title={title}
      actions={
        <Button variant="link" onClick={onRetry}>
          {t("common.grid.retry")}
        </Button>
      }
    >
      {problem instanceof ApiProblem ? <p>{problem.title}</p> : null}
      {problem instanceof ApiProblem && problem.requestId !== null ? (
        <p>{t("contracts.drawer.reference", { reference: problem.requestId })}</p>
      ) : null}
    </Banner>
  );
}

function StatusCell({ scope, item }: { readonly scope: SearchScope; readonly item: SearchItem }) {
  const enumId = SEARCH_STATUS_ENUM[scope];
  const chip = enumId === null || item.status === null ? null : chipFor(enumId, item.status);
  return <td className={CELL}>{chip === null ? null : <StatusChip status={chip.status} />}</td>;
}

/**
 * One scope's table (SCREENS §1.4): the first page the search answered and the pages "Show more"
 * has read since, each from the cursor of the page before it. The pages are kept under the cursor
 * the first page ended with, so another answer of the first page starts its own.
 */
function ScopeTable({ q, group }: { readonly q: string; readonly group: SearchGroup }) {
  const { scope } = group;
  const built = useBuiltPaths();
  const linked = built.has(RECORD_ROUTE_PATTERNS[scope]);
  const more = useInfiniteQuery({
    queryKey: queryKey("search-more", "tenant", {
      q,
      scope,
      limit: RESULTS_LIMIT,
      from: group.next_cursor,
    }),
    queryFn: ({ pageParam }) => fetchSearchScope(q, scope, RESULTS_LIMIT, pageParam),
    initialPageParam: group.next_cursor,
    getNextPageParam: (last) => last.next_cursor ?? undefined,
    // Read on "Show more" alone.
    enabled: false,
    retry: false,
  });
  const items = useMemo(
    () => [...group.items, ...(more.data?.pages ?? []).flatMap((page) => page.items)],
    [group.items, more.data],
  );
  const last = more.data?.pages.at(-1);
  const next = last === undefined ? group.next_cursor : last.next_cursor;
  // The route of an obligation needs its contract (SCREENS §1.4): one read a row shown, kept for
  // the session — an obligation does not change its contract.
  const contracts = useQueries({
    queries: (scope === "obligations" && linked ? items : []).map((item) => ({
      queryKey: obligationContractKey(item.id),
      queryFn: () => fetchObligationContract(item.id),
      staleTime: Number.POSITIVE_INFINITY,
      retry: false,
    })),
  });
  const routeOf = (item: SearchItem, index: number): string | null => {
    if (!linked) {
      return null;
    }
    if (scope !== "obligations") {
      return recordRoute(scope, item);
    }
    const contractId = contracts[index]?.data;
    return contractId === undefined ? null : obligationRoute(contractId, item.id);
  };
  const status = SEARCH_STATUS_ENUM[scope] !== null;
  return (
    <section data-testid={`SF-24-results-${scope}`} className="flex flex-col gap-2">
      <table className="w-full border-collapse text-body-sm">
        <caption className="pb-2 text-start text-title-sm text-fg-1">{scopeLabel(scope)}</caption>
        <thead>
          <tr className="border-b border-default text-caption text-fg-3">
            <th scope="col" className={`${HEAD} w-72`}>
              {t(`search.results.column.${scope}.primary`)}
            </th>
            <th scope="col" className={HEAD}>
              {t(`search.results.column.${scope}.secondary`)}
            </th>
            {status ? (
              <th scope="col" className={`${HEAD} w-48`}>
                {t(`search.results.column.${scope}.status`)}
              </th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {items.map((item, index) => {
            const route = routeOf(item, index);
            return (
              <tr key={item.id} className="border-b border-hairline">
                <th
                  scope="row"
                  className={`${CELL} text-start font-normal`}
                  aria-busy={contracts[index]?.isPending === true || undefined}
                >
                  {route === null ? (
                    <span className={MONO}>{item.primary}</span>
                  ) : (
                    <Link to={route} className={MONO_LINK}>
                      {item.primary}
                    </Link>
                  )}
                </th>
                <td className={CELL}>
                  {scope === "invoices" || scope === "journals" ? (
                    <span className={MONO}>{item.secondary}</span>
                  ) : (
                    <span className="text-fg-1">{item.secondary}</span>
                  )}
                </td>
                {status ? <StatusCell scope={scope} item={item} /> : null}
              </tr>
            );
          })}
        </tbody>
      </table>
      {more.isError ? (
        <LoadError
          title={t("search.results.moreError")}
          problem={more.error}
          onRetry={() => void more.fetchNextPage()}
        />
      ) : null}
      {next === null || more.isError ? null : (
        <div>
          <Button
            variant="secondary"
            size="sm"
            loading={more.isFetching}
            onClick={() => void more.fetchNextPage()}
          >
            {t(`search.results.showMore.${scope}`)}
          </Button>
        </div>
      )}
    </section>
  );
}

function Results({ q, scope }: { readonly q: string; readonly scope: SearchScope | null }) {
  const results = useQuery({
    queryKey: searchKey(q, scope, RESULTS_LIMIT),
    queryFn: async (): Promise<readonly SearchGroup[]> =>
      scope === null
        ? fetchSearch(q, RESULTS_LIMIT)
        : [await fetchSearchScope(q, scope, RESULTS_LIMIT, null)],
  });
  if (results.isError) {
    return (
      <LoadError
        title={t("search.results.loadError")}
        problem={results.error}
        onRetry={() => void results.refetch()}
      />
    );
  }
  if (results.data === undefined) {
    return <Skeleton region={t("search.results.title")} shape="rows" count={8} />;
  }
  const found = results.data.filter((group) => group.items.length > 0);
  if (found.length === 0) {
    return (
      <p data-testid="SF-24-no-matches" className="text-body-sm text-fg-2">
        {t("search.noMatches", { query: q })}
      </p>
    );
  }
  return (
    <div className="flex flex-col gap-6">
      {found.map((group) => (
        // Another answer of the first page is another list: its later pages start again.
        <ScopeTable key={`${group.scope}:${group.next_cursor ?? ""}`} q={q} group={group} />
      ))}
    </div>
  );
}

export function SearchResults() {
  const location = useLocation();
  const me = useMe();
  const access = useAccess();
  const fields = useMemo(
    (): readonly FilterField[] => [
      {
        name: SCOPE_FIELD,
        label: t("search.results.scope"),
        kind: "enum",
        operators: ["is"],
        options: SEARCH_SCOPES.map((value) => ({ value, label: scopeLabel(value) })),
      },
    ],
    [],
  );
  const parsed = useMemo(() => parseFilters(location.search, fields), [location.search, fields]);
  const chip = parsed.filters.find((filter) => filter.field === SCOPE_FIELD)?.values[0];
  const scope = isSearchScope(chip) ? chip : null;
  const text = parsed.query.trim();
  const q = searchable(parsed.query);

  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={t("search.results.title")} shape="rows" count={8} />;
  } else if (!access.holdsAnywhere(SEARCH_PERMISSION)) {
    // 04 API-R-55: the route asks `contract.read`, for any entity.
    body = (
      <EmptyState
        title={t("settings.access.title", { area: t("search.access.area") })}
        description={t("settings.access.description", {
          permission: t("settings.access.permission.contractRead"),
        })}
      />
    );
  } else {
    body = (
      <>
        <FilterBar
          fields={fields}
          searchLabel={t("search.results.searchLabel")}
          testId="SF-24-filters"
        />
        {q === null ? (
          <p data-testid="SF-24-too-short" className="text-body-sm text-fg-2">
            {t("search.tooShort")}
          </p>
        ) : (
          <Results q={q} scope={scope} />
        )}
      </>
    );
  }
  return (
    <div data-testid="SF-24-results-page" className="flex flex-col gap-4">
      <h1 tabIndex={-1} className="text-title-lg text-fg-1">
        {text === "" ? t("search.results.title") : t("search.results.heading", { query: text })}
      </h1>
      {body}
    </div>
  );
}
