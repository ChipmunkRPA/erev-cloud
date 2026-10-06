// Currencies and FX rates (04 API-R-19 `GET /currencies`, `GET, PUT /tenant-currencies`, `GET, POST
// /fx-rate-sets`, `GET, POST /fx-rate-sets/{id}/versions`, `GET, PATCH /fx-rate-set-versions/{id}`,
// `POST /fx-rate-set-versions/{id}/submit`, `/withdraw`, `GET /fx-rates`; T-REF-08 to T-REF-11; E-12;
// REQ-REF-004 to REQ-REF-006; D-25; SCREENS_B §9.4; BUILD_SPEC RFD-18). Enabled currencies are one
// tenant list saved whole; FX rate sets hold immutable approved versions of spot, closing or average
// rates. Commands go through `useCommand` from the screen.
import { useQuery } from "@tanstack/react-query";

import type { EditOutcome } from "../../../components/data-grid/types";
import { t } from "../../i18n/t";
import { api, unwrap } from "../client";
import type { CommandKeys } from "../commands";
import { fetchListPage } from "../lists";
import { fieldErrorsOf, readProblem } from "../problems";
import { queryKey, type QueryKey } from "../query-keys";
import type { components } from "../schema";
import { STRUCTURE_LIMIT } from "./tenant";

export type Currency = components["schemas"]["CurrencyOut"];
export type TenantCurrency = components["schemas"]["TenantCurrencyOut"];
export type TenantCurrenciesUpdate = components["schemas"]["TenantCurrenciesIn"];
export type FxRateSet = components["schemas"]["FxRateSetOut"];
export type FxRateSetCreate = components["schemas"]["FxRateSetIn"];
export type FxRateSetVersion = components["schemas"]["FxRateSetVersionOut"];
export type FxRateSetVersionDetail = components["schemas"]["FxRateSetVersionDetailOut"];
export type FxRateSetVersionCreate = components["schemas"]["FxRateSetVersionIn"];
export type FxRateSetVersionUpdate = components["schemas"]["FxRateSetVersionUpdateIn"];
export type FxRate = components["schemas"]["FxRateOut"];
export type FxRateCreate = components["schemas"]["FxRateIn"];
export type RateType = components["schemas"]["RateType"];
export type ConfigStatus = components["schemas"]["ConfigStatus"];

export const CURRENCIES_PATH = "/api/v1/currencies";
export const TENANT_CURRENCIES_PATH = "/api/v1/tenant-currencies";
export const FX_RATE_SETS_PATH = "/api/v1/fx-rate-sets";
export const FX_RATE_SET_VERSIONS_PATH = "/api/v1/fx-rate-set-versions";
/** SCREENS RT-77 SF-15:currencies; screen parameters `rate_set=<code>` and `version=<n>` (SCR-URL-27). */
export const CURRENCIES_ROUTE = "/settings/currencies";
/** SCREENS_B §9.4: enabling currencies needs `settings.manage`. */
export const CURRENCIES_MANAGE_PERMISSION = "settings.manage";
/** SCREENS_B §9.4: rate sets, versions and rates need any of these (04 API-R-19 rev 1.2). */
export const RATES_AUTHOR_PERMISSIONS: readonly string[] = ["config.author", "masterdata.maintain"];
/** T-REF-10 `rate_type` literals in 04 order. */
export const RATE_TYPES: readonly RateType[] = ["spot", "closing", "average"];
/** SCREENS_B §9.4 "New rate set" code rule. */
export const RATE_SET_CODE_PATTERN = /^[A-Za-z0-9-]+$/;
/** A version stays editable while it is a draft (ERR-09 otherwise). */
export const DRAFT_STATUS: ConfigStatus = "DRAFT";

export const EVERY_TENANT_CURRENCY: QueryKey = queryKey("tenant-currencies", "tenant");
export const EVERY_FX_RATE_SET: QueryKey = queryKey("fx-rate-sets", "tenant");
export const EVERY_FX_VERSION: QueryKey = queryKey("fx-rate-set-versions", "tenant");

export function currenciesKey(): QueryKey {
  return queryKey("currencies", "public", { view: "active" });
}

/** The ISO 4217 catalogue of active currencies, in code order. */
export async function fetchActiveCurrencies(): Promise<readonly Currency[]> {
  const page = await fetchListPage<Currency>(CURRENCIES_PATH, { is_active: true }, null, {
    limit: STRUCTURE_LIMIT,
    count: false,
  });
  return page.items;
}

export function tenantCurrenciesKey(): QueryKey {
  return queryKey("tenant-currencies", "tenant", { view: "all" });
}

/** The tenant's currency rows (enabled and reporting flags). */
export async function fetchTenantCurrencies(): Promise<readonly TenantCurrency[]> {
  const page = await fetchListPage<TenantCurrency>(TENANT_CURRENCIES_PATH, {}, null, {
    limit: STRUCTURE_LIMIT,
    count: false,
  });
  return page.items;
}

export function useTenantCurrencies(enabled = true) {
  return useQuery({ queryKey: tenantCurrenciesKey(), queryFn: fetchTenantCurrencies, enabled });
}

/** The enabled currency codes in code order (the entity drawer's "Functional currency" options). */
export function enabledCurrencyCodes(rows: readonly TenantCurrency[]): readonly string[] {
  return rows
    .filter((row) => row.is_enabled)
    .map((row) => row.currency_code)
    .sort((a, b) => a.localeCompare(b));
}

export function fxRateSetsKey(): QueryKey {
  return queryKey("fx-rate-sets", "tenant", { view: "all" });
}

export async function fetchFxRateSets(): Promise<readonly FxRateSet[]> {
  const page = await fetchListPage<FxRateSet>(FX_RATE_SETS_PATH, {}, null, {
    limit: STRUCTURE_LIMIT,
    count: false,
  });
  return page.items;
}

export function fxVersionsPath(setId: string): string {
  return `${FX_RATE_SETS_PATH}/${setId}/versions`;
}

export function fxVersionsKey(setId: string): QueryKey {
  return queryKey("fx-rate-set-versions", "tenant", { set: setId });
}

/** The versions of one rate set, newest first. */
export async function fetchFxVersions(setId: string): Promise<readonly FxRateSetVersion[]> {
  const page = await fetchListPage<FxRateSetVersion>(
    fxVersionsPath(setId),
    { sort: "-version_no" },
    null,
    {
      limit: STRUCTURE_LIMIT,
      count: false,
    },
  );
  return page.items;
}

export function fxVersionPath(versionId: string): string {
  return `${FX_RATE_SET_VERSIONS_PATH}/${versionId}`;
}

export function fxVersionCommandPath(versionId: string, command: "submit" | "withdraw"): string {
  return `${fxVersionPath(versionId)}/${command}`;
}

export function fxVersionKey(versionId: string): QueryKey {
  return queryKey("fx-rate-set-versions", "tenant", { version: versionId });
}

export function fetchFxVersion(versionId: string): Promise<FxRateSetVersionDetail> {
  return unwrap(
    api.GET("/api/v1/fx-rate-set-versions/{version_id}", {
      params: { path: { version_id: versionId } },
    }),
  );
}

/** The rate set whose code matches, else the first one. */
export function selectRateSet(sets: readonly FxRateSet[], code: string | null): FxRateSet | null {
  return sets.find((set) => set.code === code) ?? sets[0] ?? null;
}

/** The version whose number matches, else the newest one. */
export function selectVersion(
  versions: readonly FxRateSetVersion[],
  versionNo: number | null,
): FxRateSetVersion | null {
  return versions.find((version) => version.version_no === versionNo) ?? versions[0] ?? null;
}

/** The newest approved or published version, for the set's summary line. */
export function latestApproved(versions: readonly FxRateSetVersion[]): FxRateSetVersion | null {
  return (
    versions.find((version) => version.status === "APPROVED" || version.status === "PUBLISHED") ??
    null
  );
}

export function currenciesRoute(setCode: string | null, versionNo: number | null): string {
  const params = new URLSearchParams();
  if (setCode !== null) {
    params.set("rate_set", setCode);
  }
  if (versionNo !== null) {
    params.set("version", String(versionNo));
  }
  const search = params.toString();
  return search === "" ? CURRENCIES_ROUTE : `${CURRENCIES_ROUTE}?${search}`;
}

/** SCREENS_B §9.4 rate row test key `<base>-<quote>-<period_key>` (the effective date when no period). */
export function rateRowKey(rate: FxRate): string {
  return `${rate.base_currency}-${rate.quote_currency}-${rate.period_key ?? rate.effective_date}`;
}

/** REQ-REF-005: a rate is a decimal above zero. */
export function ratePositive(text: string): boolean {
  return /^\d+(\.\d+)?$/.test(text.trim()) && Number(text) > 0;
}

/** SF-10:new with the FX rates template (REQ-REF-006; BUILD_SPEC DIN-16 `?template=`). */
export const IMPORT_NEW_ROUTE = "/data/imports/new";
export const FX_RATES_TEMPLATE = "fx_rates";

export function uploadRatesRoute(): string {
  return `${IMPORT_NEW_ROUTE}?template=${FX_RATES_TEMPLATE}`;
}

/** The `FxRateIn` body of an existing rate, with one rate value replaced. */
export function rateInputs(
  rates: readonly FxRate[],
  changed: FxRate,
  value: string,
): readonly FxRateCreate[] {
  return rates.map((rate) => ({
    base_currency: rate.base_currency,
    quote_currency: rate.quote_currency,
    effective_date: rate.effective_date,
    period_key: rate.period_key,
    rate: rate.id === changed.id ? value : rate.rate,
  }));
}

/**
 * SCREENS_B §9.4 inline edit of a draft rate: `PATCH /fx-rate-set-versions/{id}` replaces the rates,
 * under the key `keys` holds for that body (DG-FE-05 rev 1.156).
 */
export async function saveVersionRates(
  keys: CommandKeys,
  version: Pick<FxRateSetVersionDetail, "id" | "row_version" | "rates">,
  changed: FxRate,
  value: string,
): Promise<EditOutcome> {
  const body: FxRateSetVersionUpdate = { rates: [...rateInputs(version.rates, changed, value)] };
  let response: Response;
  try {
    response = await keys.send("PATCH", fxVersionPath(version.id), {
      body,
      headers: { "If-Match": `"r${String(version.row_version)}"` },
    });
  } catch {
    // No answer: the cell says so, and the same rate saved again carries the same key.
    return { ok: false, message: t("common.command.noAnswer") };
  }
  if (response.ok) {
    return { ok: true };
  }
  const problem = await readProblem(response);
  const [first] = Object.values(fieldErrorsOf(problem));
  return { ok: false, message: first ?? problem.detail ?? problem.title };
}
