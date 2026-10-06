// SF-15:currencies Currencies and rates (SCREENS_B §9.4; SCREENS §0.4 RT-77, §0.5 SCR-URL-27 `rate_set`,
// `version`, §0.7 SCR-ST-03, SCR-PERM-01, SCR-PERM-02; §0.8 E-12; DESIGN_SYSTEM DS-CMP-10, DS-CMP-11,
// DS-CMP-21, DS-CMP-29, DS-FMT-14; 04 API-R-19 `GET /currencies`, `GET, PUT /tenant-currencies`, `GET, POST
// /fx-rate-sets`, `GET, POST /fx-rate-sets/{id}/versions`, `GET, PATCH /fx-rate-set-versions/{id}`,
// `POST /fx-rate-set-versions/{id}/submit`; REQ-REF-004 to REQ-REF-006; D-25; BUILD_SPEC RFD-18). The
// Settings frame with the Workspace route tabs, the static table "Enabled currencies" (checkboxes applied
// on "Save currencies", `settings.manage`) and the region "FX rate sets": the rate set select (`rate_set`),
// its summary and latest approved version, the version tabs (`version`), "New rate set", "New version",
// "Upload rates CSV" (SF-10:new once built), "Submit for approval" and the DataGrid "Rates" (inline
// editable while the version is a draft; "Enter a rate above 0."). Rate set and version commands need
// `config.author` or `masterdata.maintain`. "Withdraw" and the pair filter of the rates read are not
// built here.
import { useQuery } from "@tanstack/react-query";
import { type FormEvent, type ReactNode, useId, useMemo, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import { type GridColumn, type GridSource } from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { Combobox } from "../../components/form/Combobox";
import { DateInput } from "../../components/form/DateInput";
import { controlClass, Field } from "../../components/form/Field";
import { Select } from "../../components/form/Select";
import { PanelTabs } from "../../components/record/Tabs";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { chipFor } from "../../components/ui/StatusChip";
import { type Access, useAccess } from "../../lib/access";
import { type CommandKeys, useCommand, useCommandKeys } from "../../lib/api/commands";
import {
  type ConfigStatus,
  CURRENCIES_MANAGE_PERMISSION,
  currenciesKey,
  currenciesRoute,
  DRAFT_STATUS,
  EVERY_FX_RATE_SET,
  EVERY_FX_VERSION,
  EVERY_TENANT_CURRENCY,
  fetchActiveCurrencies,
  fetchFxRateSets,
  fetchFxVersion,
  fetchFxVersions,
  FX_RATE_SETS_PATH,
  type FxRate,
  type FxRateSet,
  type FxRateSetCreate,
  type FxRateSetVersion,
  type FxRateSetVersionCreate,
  type FxRateSetVersionDetail,
  fxRateSetsKey,
  fxVersionCommandPath,
  fxVersionKey,
  fxVersionsKey,
  fxVersionsPath,
  IMPORT_NEW_ROUTE,
  latestApproved,
  RATE_SET_CODE_PATTERN,
  RATE_TYPES,
  type RateType,
  ratePositive,
  rateRowKey,
  RATES_AUTHOR_PERMISSIONS,
  saveVersionRates,
  selectRateSet,
  selectVersion,
  TENANT_CURRENCIES_PATH,
  type TenantCurrency,
  uploadRatesRoute,
  useTenantCurrencies,
} from "../../lib/api/queries/currencies";
import { entitiesUsing, useAllEntities } from "../../lib/api/queries/entities";
import { useMe } from "../../lib/api/queries/me";
import { STRUCTURE_READ_PERMISSION } from "../../lib/api/queries/tenant";
import { fieldMessages, placeProblem } from "../../lib/api/refusals";
import {
  dateParts,
  daysInMonth,
  formatDate,
  formatNumber,
  formatPeriod,
  formatRate,
  NO_VALUE,
} from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { APPROVAL_REQUEST_ROUTE } from "../access/user";
import { SettingsPageHeader, useBuiltPaths } from "./index";

function yesNo(value: boolean): string {
  return t(value ? "settings.currencies.yes" : "settings.currencies.no");
}

function mono(text: string) {
  return <span className="font-mono text-mono text-fg-2">{text}</span>;
}

function statusLabel(status: ConfigStatus): string {
  return chipFor("E-12", status)?.status ?? status;
}

function rateTypeLabel(rateType: RateType): string {
  return t(`settings.currencies.rateType.${rateType}`);
}

/** DS-FMT-19 label of a rate's period: closing and average rates are dated on the period end, so a
 *  month-end effective date labels a Gregorian month ("Sep 2026"); other keys keep the fiscal label. */
export function ratePeriodLabel(rate: Pick<FxRate, "period_key" | "effective_date">): string {
  if (rate.period_key === null) {
    return NO_VALUE;
  }
  const end = dateParts(rate.effective_date);
  if (end.day === daysInMonth(end.year, end.month)) {
    const start = `${String(end.year)}-${String(end.month).padStart(2, "0")}-01`;
    return formatPeriod(rate.period_key, { startDate: start });
  }
  return formatPeriod(rate.period_key);
}

/** SCREENS_B §9.4 row header "<base> to <quote> <effective date>". */
export function rateRowHeader(rate: FxRate): string {
  return t("settings.currencies.rates.rowHeader", {
    base: rate.base_currency,
    quote: rate.quote_currency,
    date: formatDate(rate.effective_date),
  });
}

export function CurrenciesScreen() {
  const me = useMe();
  const access = useAccess();
  const title = t("settings.currencies.title");

  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={6} />;
  } else if (!access.holdsAnywhere(STRUCTURE_READ_PERMISSION)) {
    body = (
      <EmptyState
        title={t("settings.access.title", { area: title })}
        description={t("settings.access.description", {
          permission: t("settings.access.permission.configRead"),
        })}
      />
    );
  } else {
    body = <CurrenciesPage access={access} />;
  }
  return (
    <div
      data-testid="SF-15-currencies-page"
      className="flex w-full flex-col gap-6 px-[var(--gutter)] py-6"
    >
      <SettingsPageHeader title={title} group="workspace" />
      {body}
    </div>
  );
}

function CurrenciesPage({ access }: { readonly access: Access }) {
  // `PUT /tenant-currencies` is an act on the whole workspace: held for all entities.
  const manage = access.holdsForAll(CURRENCIES_MANAGE_PERMISSION);
  const author = RATES_AUTHOR_PERMISSIONS.some((permission) => access.holdsAnywhere(permission));
  return (
    <>
      <EnabledCurrencies manage={manage} />
      <RateSets author={author} />
    </>
  );
}

/** SCREENS_B §9.4 static table "Enabled currencies" with checkboxes applied on "Save currencies". */
function EnabledCurrencies({ manage }: { readonly manage: boolean }) {
  const toast = useToast();
  const headingId = useId();
  const addId = useId();
  const rows = useTenantCurrencies();
  const catalogue = useQuery({
    queryKey: currenciesKey(),
    queryFn: fetchActiveCurrencies,
    enabled: manage,
  });
  const entities = useAllEntities();
  const [draft, setDraft] = useState<ReadonlySet<string> | null>(null);
  const [added, setAdded] = useState<readonly TenantCurrency[]>([]);
  const save = useCommand({
    method: "PUT",
    path: TENANT_CURRENCIES_PATH,
    invalidates: [EVERY_TENANT_CURRENCY],
  });
  const stored = useMemo(
    () =>
      new Set((rows.data ?? []).filter((row) => row.is_enabled).map((row) => row.currency_code)),
    [rows.data],
  );
  const enabled = draft ?? stored;
  const listed = useMemo(() => {
    const all = [...(rows.data ?? []), ...added];
    return all.sort((a, b) => a.currency_code.localeCompare(b.currency_code));
  }, [rows.data, added]);
  const dirty =
    draft !== null && (draft.size !== stored.size || [...draft].some((code) => !stored.has(code)));
  const usedBy = (code: string) => entitiesUsing(entities.data ?? [], code);
  const toggle = (code: string, next: boolean) => {
    setDraft((previous) => {
      const set = new Set(previous ?? stored);
      if (next) {
        set.add(code);
      } else {
        set.delete(code);
      }
      return set;
    });
  };
  const addOptions = (catalogue.data ?? [])
    .filter((currency) => !listed.some((row) => row.currency_code === currency.code))
    .map((currency) => ({ value: currency.code, label: `${currency.code} · ${currency.name}` }));
  const add = (code: string | null) => {
    const currency = catalogue.data?.find((candidate) => candidate.code === code);
    if (currency === undefined) {
      return;
    }
    setAdded((previous) => [
      ...previous,
      {
        currency_code: currency.code,
        name: currency.name,
        minor_unit: currency.minor_unit,
        is_enabled: false,
        is_reporting_currency: false,
        row_version: 0,
        created_at: "",
        updated_at: "",
      },
    ]);
    toggle(currency.code, true);
  };
  const submit = async () => {
    const outcome = await save.submit({ currency_codes: [...enabled].sort() });
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("settings.currencies.enabled.saved") });
      setDraft(null);
      setAdded([]);
    }
  };

  let body: ReactNode;
  if (rows.isError) {
    body = <Banner tone="negative" title={t("settings.currencies.enabled.loadError")} />;
  } else if (rows.data === undefined) {
    body = <Skeleton region={t("settings.currencies.enabled.title")} shape="rows" count={4} />;
  } else {
    body = (
      <>
        <RefusalBanner problem={save.problem} />
        <table
          aria-labelledby={headingId}
          data-testid="SF-15-grid-currencies"
          className="w-full text-body-sm"
        >
          <thead>
            <tr className="border-b border-hairline text-start text-caption text-fg-3">
              <th scope="col" className="py-2 pe-4 text-start font-medium">
                {t("settings.currencies.enabled.column.code")}
              </th>
              <th scope="col" className="py-2 pe-4 text-start font-medium">
                {t("settings.currencies.enabled.column.name")}
              </th>
              <th scope="col" className="py-2 pe-4 text-end font-medium">
                {t("settings.currencies.enabled.column.minorUnit")}
              </th>
              <th scope="col" className="py-2 pe-4 text-start font-medium">
                {t("settings.currencies.enabled.column.enabled")}
              </th>
              <th scope="col" className="py-2 text-start font-medium">
                {t("settings.currencies.enabled.column.usedBy")}
              </th>
            </tr>
          </thead>
          <tbody>
            {listed.length === 0 ? (
              <tr>
                <td colSpan={5} className="py-3 text-fg-3">
                  {t("settings.currencies.enabled.empty")}
                </td>
              </tr>
            ) : (
              listed.map((row) => {
                const users = usedBy(row.currency_code);
                const locked = row.is_reporting_currency || users.length > 0;
                return (
                  <tr
                    key={row.currency_code}
                    data-testid={`SF-15-currency-${row.currency_code}`}
                    className="border-b border-hairline last:border-b-0"
                  >
                    <th scope="row" className="py-2 pe-4 text-start font-normal">
                      {mono(row.currency_code)}
                    </th>
                    <td className="py-2 pe-4 text-fg-1">{row.name}</td>
                    <td className="num py-2 pe-4 text-end text-fg-1">{String(row.minor_unit)}</td>
                    <td className="py-2 pe-4">
                      <input
                        type="checkbox"
                        aria-label={t("settings.currencies.enabled.toggle", {
                          code: row.currency_code,
                        })}
                        checked={enabled.has(row.currency_code)}
                        disabled={!manage || (locked && enabled.has(row.currency_code))}
                        title={
                          row.is_reporting_currency
                            ? t("settings.currencies.enabled.reporting")
                            : users.length > 0
                              ? t("settings.currencies.enabled.inUse")
                              : undefined
                        }
                        onChange={(event) => toggle(row.currency_code, event.target.checked)}
                        className="size-4"
                      />
                    </td>
                    <td className="py-2 text-fg-2">
                      {users.length === 0 ? (
                        <span className="text-fg-3">{NO_VALUE}</span>
                      ) : (
                        mono(users.join(", "))
                      )}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
        {manage ? (
          <div className="flex flex-wrap items-end justify-between gap-3">
            <Field
              name={`add-currency-${addId}`}
              label={t("settings.currencies.enabled.add")}
              width="text"
            >
              {(control) => (
                <Combobox control={control} options={addOptions} value={null} onChange={add} />
              )}
            </Field>
            <Button
              variant="primary"
              disabledReason={dirty ? undefined : t("settings.currencies.enabled.noChanges")}
              onClick={() => void submit()}
            >
              {save.pending
                ? `${t("settings.currencies.enabled.save")}…`
                : t("settings.currencies.enabled.save")}
            </Button>
          </div>
        ) : null}
      </>
    );
  }
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-3">
      <h2 id={headingId} className="border-b border-hairline pb-2 text-title-sm text-fg-1">
        {t("settings.currencies.enabled.title")}
      </h2>
      {body}
    </section>
  );
}

type Dialog =
  | { readonly kind: "none" }
  | { readonly kind: "new-set" }
  | { readonly kind: "new-version"; readonly set: FxRateSet }
  | {
      readonly kind: "submit";
      readonly set: FxRateSet;
      readonly version: FxRateSetVersion;
      readonly rateCount: number;
    };

/** SCREENS_B §9.4 region "FX rate sets". */
function RateSets({ author }: { readonly author: boolean }) {
  const headingId = useId();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const sets = useQuery({ queryKey: fxRateSetsKey(), queryFn: fetchFxRateSets });
  const [dialog, setDialog] = useState<Dialog>({ kind: "none" });
  const selected = selectRateSet(sets.data ?? [], params.get("rate_set"));
  const versionParam = params.get("version");
  const versionNo =
    versionParam === null || !/^\d+$/.test(versionParam) ? null : Number(versionParam);
  const close = () => setDialog({ kind: "none" });
  const go = (code: string | null, version: number | null) =>
    void navigate(currenciesRoute(code, version), { replace: true });
  const newSet = author
    ? {
        label: t("settings.currencies.rateSets.new"),
        onAction: () => setDialog({ kind: "new-set" }),
      }
    : undefined;

  let body: ReactNode;
  if (sets.isError) {
    body = <Banner tone="negative" title={t("settings.currencies.rateSets.loadError")} />;
  } else if (sets.data === undefined) {
    body = <Skeleton region={t("settings.currencies.rateSets.title")} shape="rows" count={4} />;
  } else if (sets.data.length === 0 || selected === null) {
    body = (
      <div data-testid="SF-15-empty-rate-sets">
        <EmptyState
          title={t("settings.currencies.rateSets.empty.title")}
          description={t("settings.currencies.rateSets.empty.description")}
          action={newSet}
        />
      </div>
    );
  } else {
    body = (
      <RateSetDetail
        sets={sets.data}
        set={selected}
        versionNo={versionNo}
        author={author}
        onSelectSet={(code) => go(code, null)}
        onSelectVersion={(version) => go(selected.code, version)}
        onNewVersion={() => setDialog({ kind: "new-version", set: selected })}
        onSubmit={(version, rateCount) =>
          setDialog({ kind: "submit", set: selected, version, rateCount })
        }
      />
    );
  }
  return (
    <section
      aria-labelledby={headingId}
      data-testid="SF-15-rate-sets"
      className="flex min-h-0 flex-col gap-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-hairline pb-2">
        <h2 id={headingId} className="text-title-sm text-fg-1">
          {sets.data === undefined
            ? t("settings.currencies.rateSets.title")
            : t("settings.currencies.rateSets.titleCount", {
                formatted: formatNumber(sets.data.length, { kind: "count" }),
              })}
        </h2>
        {newSet === undefined || sets.data === undefined || sets.data.length === 0 ? null : (
          <Button variant="secondary" size="sm" onClick={newSet.onAction}>
            {newSet.label}
          </Button>
        )}
      </div>
      {body}
      {dialog.kind === "new-set" ? (
        <NewRateSetModal
          onClose={close}
          onCreated={(set) => {
            close();
            go(set.code, null);
          }}
        />
      ) : null}
      {dialog.kind === "new-version" ? (
        <NewVersionModal
          set={dialog.set}
          onClose={close}
          onCreated={(version) => {
            close();
            go(dialog.set.code, version.version_no);
          }}
        />
      ) : null}
      {dialog.kind === "submit" ? (
        <SubmitVersionModal
          set={dialog.set}
          version={dialog.version}
          rateCount={dialog.rateCount}
          onClose={close}
        />
      ) : null}
    </section>
  );
}

interface RateSetDetailProps {
  readonly sets: readonly FxRateSet[];
  readonly set: FxRateSet;
  readonly versionNo: number | null;
  readonly author: boolean;
  readonly onSelectSet: (code: string) => void;
  readonly onSelectVersion: (version: number) => void;
  readonly onNewVersion: () => void;
  readonly onSubmit: (version: FxRateSetVersion, rateCount: number) => void;
}

function RateSetDetail({
  sets,
  set,
  versionNo,
  author,
  onSelectSet,
  onSelectVersion,
  onNewVersion,
  onSubmit,
}: RateSetDetailProps) {
  const selectId = useId();
  const versions = useQuery({
    queryKey: fxVersionsKey(set.id),
    queryFn: () => fetchFxVersions(set.id),
  });
  const version = selectVersion(versions.data ?? [], versionNo);
  const approved = latestApproved(versions.data ?? []);
  return (
    <div className="flex min-h-0 flex-col gap-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <Field
          name={`rate-set-${selectId}`}
          label={t("settings.currencies.rateSets.select")}
          width="text"
        >
          {(control) => (
            <Select<string>
              control={control}
              options={sets.map((candidate) => ({
                value: candidate.code,
                // A join of three values rather than a catalogue template.
                label: `${candidate.code} · ${rateTypeLabel(candidate.rate_type)} · ${candidate.source}`,
              }))}
              value={set.code}
              onChange={onSelectSet}
            />
          )}
        </Field>
        <p className="text-body-sm text-fg-2">
          {approved === null
            ? t("settings.currencies.rateSets.noneApproved")
            : t("settings.currencies.rateSets.latestApproved", {
                version: String(approved.version_no),
                from: formatDate(approved.coverage_from),
                to: formatDate(approved.coverage_to),
              })}
        </p>
      </div>
      {versions.isError ? (
        <Banner tone="negative" title={t("settings.currencies.versions.loadError")} />
      ) : versions.data === undefined ? (
        <Skeleton region={t("settings.currencies.versions.label")} shape="rows" count={3} />
      ) : version === null ? (
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-body-sm text-fg-3">{t("settings.currencies.versions.none")}</p>
          {author ? (
            <Button variant="secondary" size="sm" onClick={onNewVersion}>
              {t("settings.currencies.versions.new")}
            </Button>
          ) : null}
        </div>
      ) : (
        <PanelTabs
          label={t("settings.currencies.versions.label")}
          tabs={versions.data.map((candidate) => ({
            id: String(candidate.version_no),
            label: t("settings.currencies.versions.tab", {
              version: String(candidate.version_no),
              status: statusLabel(candidate.status),
            }),
          }))}
          selectedId={String(version.version_no)}
          onChange={(id) => onSelectVersion(Number(id))}
        >
          <VersionPane
            version={version}
            author={author}
            onNewVersion={onNewVersion}
            onSubmit={onSubmit}
          />
        </PanelTabs>
      )}
    </div>
  );
}

interface VersionPaneProps {
  readonly version: FxRateSetVersion;
  readonly author: boolean;
  readonly onNewVersion: () => void;
  readonly onSubmit: (version: FxRateSetVersion, rateCount: number) => void;
}

function VersionPane({ version, author, onNewVersion, onSubmit }: VersionPaneProps) {
  const built = useBuiltPaths();
  const detail = useQuery({
    queryKey: fxVersionKey(version.id),
    queryFn: () => fetchFxVersion(version.id),
  });
  const draft = version.status === DRAFT_STATUS;
  const editable = author && draft;
  const keys = useCommandKeys();
  const columns = useMemo(
    () => rateColumns(editable ? (detail.data ?? null) : null, keys),
    [editable, detail.data, keys],
  );
  const source: GridSource<FxRate> = useMemo(
    () => ({
      queryKey: fxVersionKey(version.id),
      fetchPage: async () => {
        const loaded = await fetchFxVersion(version.id);
        return {
          items: loaded.rates,
          nextCursor: null,
          total: { count: loaded.rates.length, capped: false },
        };
      },
    }),
    [version.id],
  );
  const countLabel = (value: number, formatted: string) =>
    t("settings.currencies.rates.count", { count: value, formatted });
  const pendingRequest = version.pending_approval_request_id ?? version.approval_request_id;
  const emptyRates = (
    <div data-testid="SF-15-empty-rates">
      <EmptyState
        title={t(
          draft
            ? "settings.currencies.rates.empty.title"
            : "settings.currencies.rates.emptyApproved.title",
        )}
        description={t(
          draft
            ? "settings.currencies.rates.empty.description"
            : "settings.currencies.rates.emptyApproved.description",
        )}
      />
    </div>
  );
  return (
    <div className="flex min-h-0 flex-col gap-3 pt-3" data-testid="SF-15-pane-version">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-body-sm text-fg-2">
          {t("settings.currencies.versions.coverage", {
            from: formatDate(version.coverage_from),
            to: formatDate(version.coverage_to),
            formatted: formatNumber(version.rate_count, { kind: "count" }),
          })}
        </p>
        <div className="flex flex-wrap items-center gap-2">
          {author ? (
            <Button variant="secondary" size="sm" onClick={onNewVersion}>
              {t("settings.currencies.versions.new")}
            </Button>
          ) : null}
          {editable && built.has(IMPORT_NEW_ROUTE) ? (
            <Link
              to={uploadRatesRoute()}
              className="text-body-sm font-medium text-accent-fg hover:underline"
            >
              {t("settings.currencies.versions.upload")}
            </Link>
          ) : null}
          {editable ? (
            <Button
              variant="primary"
              size="sm"
              onClick={() => onSubmit(version, detail.data?.rate_count ?? version.rate_count)}
            >
              {t("settings.currencies.versions.submit")}
            </Button>
          ) : null}
        </div>
      </div>
      {version.status === "SUBMITTED" ? (
        <Banner
          tone="info"
          title={t("settings.currencies.versions.pending", { version: String(version.version_no) })}
          actions={
            pendingRequest !== null && built.has(APPROVAL_REQUEST_ROUTE) ? (
              <Link
                to={`/approvals/requests/${pendingRequest}`}
                className="text-body-sm font-medium text-accent-fg hover:underline"
              >
                {t("settings.currencies.versions.reviewInApprovals")}
              </Link>
            ) : undefined
          }
        />
      ) : null}
      {draft ? null : (
        <Banner tone="info" announce="static" title={t("settings.currencies.versions.readOnly")} />
      )}
      <div className="flex min-h-0 flex-1 flex-col">
        <DataGrid<FxRate>
          name="rates"
          title={t("settings.currencies.rates.grid")}
          errorTitle={t("settings.currencies.rates.loadError")}
          countLabel={countLabel}
          columns={columns}
          source={source}
          rowKey={(rate) => rate.id}
          rowLabel={rateRowHeader}
          testIdPrefix="SF-15"
          rowTestKey={rateRowKey}
          editable={editable}
          emptyState={emptyRates}
          noResults={emptyRates}
        />
      </div>
    </div>
  );
}

/**
 * SCREENS_B §9.4 rates grid columns; the rate is inline editable while `draft` is a loaded draft, and
 * a save goes out under the key `keys` holds for it (DG-FE-05 rev 1.156).
 */
export function rateColumns(
  draft: FxRateSetVersionDetail | null,
  keys: CommandKeys,
): readonly GridColumn<FxRate>[] {
  return [
    {
      id: "base_currency",
      header: t("settings.currencies.rates.column.base"),
      kind: "identifier",
      value: (rate) => rate.base_currency,
      render: (rate) => (
        <span className="font-mono text-mono">
          {rate.base_currency}
          <span className="sr-only">{rateRowHeader(rate).slice(rate.base_currency.length)}</span>
        </span>
      ),
      width: 96,
    },
    {
      id: "quote_currency",
      header: t("settings.currencies.rates.column.quote"),
      kind: "text",
      value: (rate) => rate.quote_currency,
      render: (rate) => mono(rate.quote_currency),
      width: 96,
    },
    {
      id: "effective_date",
      header: t("settings.currencies.rates.column.effectiveDate"),
      kind: "date",
      value: (rate) => rate.effective_date,
      render: (rate) => <span className="num">{formatDate(rate.effective_date)}</span>,
    },
    {
      id: "period",
      header: t("settings.currencies.rates.column.period"),
      kind: "period",
      value: (rate) => rate.period_key,
      render: (rate) => <span className="num">{ratePeriodLabel(rate)}</span>,
      width: 112,
    },
    {
      id: "rate",
      header: t("settings.currencies.rates.column.rate"),
      kind: "number",
      value: (rate) => rate.rate,
      render: (rate) => <span className="num">{formatRate(rate.rate, { kind: "fx" })}</span>,
      edit:
        draft === null
          ? undefined
          : {
              kind: "decimal",
              save: async (rate, value) => {
                if (!ratePositive(value)) {
                  return { ok: false, message: t("settings.currencies.rates.positive") };
                }
                return saveVersionRates(keys, draft, rate, value);
              },
            },
      width: 160,
    },
    {
      id: "is_derived",
      header: t("settings.currencies.rates.column.derived"),
      kind: "text",
      value: (rate) => yesNo(rate.is_derived),
      width: 88,
    },
  ];
}

/** SCREENS_B §9.4 "New rate set" form modal. */
// docs/dev-guide.md DG-FE-06: the fields of "New rate set" and of "New version" and the members each
// sends. The two dates of a version's coverage share one place for a message, under "From".
const RATE_SET_MEMBERS = {
  code: ["code"],
  name: ["name"],
  rate_type: ["rate_type"],
  source: ["source"],
} as const;
const RATE_VERSION_MEMBERS = { coverage: ["coverage_from", "coverage_to"] } as const;

function NewRateSetModal({
  onClose,
  onCreated,
}: {
  readonly onClose: () => void;
  readonly onCreated: (set: FxRateSet) => void;
}) {
  const formId = useId();
  const toast = useToast();
  const [code, setCode] = useState("");
  const [name, setName] = useState("");
  const [rateType, setRateType] = useState<RateType | null>(null);
  const [sourceText, setSourceText] = useState("");
  const [attempted, setAttempted] = useState(false);
  const create = useCommand<FxRateSet>({
    method: "POST",
    path: FX_RATE_SETS_PATH,
    invalidates: [EVERY_FX_RATE_SET],
  });
  const placed = useMemo(() => placeProblem(create.problem, RATE_SET_MEMBERS), [create.problem]);
  const errors: Record<string, string> = { ...fieldMessages(placed.fields) };
  if (attempted) {
    if (code.trim() === "") {
      errors.code ??= t("settings.currencies.newSet.codeRequired");
    } else if (!RATE_SET_CODE_PATTERN.test(code.trim())) {
      errors.code ??= t("settings.currencies.newSet.codeRule");
    }
    if (name.trim() === "") {
      errors.name ??= t("settings.currencies.newSet.nameRequired");
    }
    if (rateType === null) {
      errors.rate_type ??= t("settings.currencies.newSet.rateTypeRequired");
    }
    if (sourceText.trim() === "") {
      errors.source ??= t("settings.currencies.newSet.sourceRequired");
    }
  }
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    if (
      code.trim() === "" ||
      !RATE_SET_CODE_PATTERN.test(code.trim()) ||
      name.trim() === "" ||
      rateType === null ||
      sourceText.trim() === ""
    ) {
      return;
    }
    const body: FxRateSetCreate = {
      code: code.trim(),
      name: name.trim(),
      rate_type: rateType,
      source: sourceText.trim(),
    };
    const outcome = await create.submit(body);
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      toast.show({
        tone: "positive",
        message: t("settings.currencies.newSet.created", { code: outcome.data.code }),
      });
      onCreated(outcome.data);
    }
  };
  return (
    <Modal
      open
      variant="form"
      title={t("settings.currencies.newSet.title")}
      primaryAction={{ label: t("settings.currencies.newSet.submit"), form: formId }}
      submitting={create.pending}
      onClose={onClose}
      testId="SF-15-dialog-new-rate-set"
    >
      <form
        id={formId}
        noValidate
        className="flex flex-col gap-3"
        onSubmit={(event) => void submit(event)}
      >
        <RefusalBanner problem={create.problem} placed={placed} />
        <Field
          name="code"
          label={t("settings.currencies.newSet.code")}
          required
          error={errors.code ?? null}
          width="text"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              className={`${controlClass(errors.code !== undefined)} font-mono`}
            />
          )}
        </Field>
        <Field
          name="name"
          label={t("settings.currencies.newSet.name")}
          required
          error={errors.name ?? null}
          width="full"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              value={name}
              onChange={(event) => setName(event.target.value)}
              className={controlClass(errors.name !== undefined)}
            />
          )}
        </Field>
        <Field
          name="rate_type"
          label={t("settings.currencies.newSet.rateType")}
          required
          error={errors.rate_type ?? null}
          width="text"
        >
          {(control) => (
            <Select<RateType>
              control={control}
              options={RATE_TYPES.map((value) => ({ value, label: rateTypeLabel(value) }))}
              value={rateType}
              invalid={errors.rate_type !== undefined}
              onChange={setRateType}
            />
          )}
        </Field>
        <Field
          name="source"
          label={t("settings.currencies.newSet.source")}
          required
          error={errors.source ?? null}
          width="text"
        >
          {(control) => (
            <input
              {...control}
              type="text"
              value={sourceText}
              onChange={(event) => setSourceText(event.target.value)}
              className={controlClass(errors.source !== undefined)}
            />
          )}
        </Field>
      </form>
    </Modal>
  );
}

/** SCREENS_B §9.4 "New version" form modal: the coverage window. */
function NewVersionModal({
  set,
  onClose,
  onCreated,
}: {
  readonly set: FxRateSet;
  readonly onClose: () => void;
  readonly onCreated: (version: FxRateSetVersion) => void;
}) {
  const formId = useId();
  const toast = useToast();
  const [fromText, setFromText] = useState("");
  const [from, setFrom] = useState<string | null>(null);
  const [toText, setToText] = useState("");
  const [to, setTo] = useState<string | null>(null);
  const [attempted, setAttempted] = useState(false);
  const create = useCommand<FxRateSetVersion>({
    method: "POST",
    path: fxVersionsPath(set.id),
    invalidates: [EVERY_FX_VERSION, EVERY_FX_RATE_SET],
  });
  const missing = from === null || to === null;
  const disordered = from !== null && to !== null && to < from;
  const placed = useMemo(
    () => placeProblem(create.problem, RATE_VERSION_MEMBERS),
    [create.problem],
  );
  const error =
    placed.fields.coverage ??
    (attempted && missing
      ? t("settings.currencies.newVersion.datesRequired")
      : attempted && disordered
        ? t("settings.currencies.newVersion.order")
        : null);
  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    if (from === null || to === null || disordered) {
      return;
    }
    const body: FxRateSetVersionCreate = { coverage_from: from, coverage_to: to };
    const outcome = await create.submit(body);
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      toast.show({
        tone: "positive",
        message: t("settings.currencies.newVersion.created", {
          code: set.code,
          version: String(outcome.data.version_no),
        }),
      });
      onCreated(outcome.data);
    }
  };
  return (
    <Modal
      open
      variant="form"
      title={t("settings.currencies.newVersion.title")}
      primaryAction={{ label: t("settings.currencies.newVersion.submit"), form: formId }}
      submitting={create.pending}
      onClose={onClose}
      testId="SF-15-dialog-new-version"
    >
      <form
        id={formId}
        noValidate
        className="flex flex-col gap-3"
        onSubmit={(event) => void submit(event)}
      >
        <RefusalBanner problem={create.problem} placed={placed} />
        <Field
          name="coverage_from"
          label={t("settings.currencies.newVersion.from")}
          required
          width="date"
          error={error}
        >
          {(control) => (
            <DateInput
              control={control}
              value={fromText}
              onChange={setFromText}
              onValue={setFrom}
              invalid={error !== null}
            />
          )}
        </Field>
        <Field
          name="coverage_to"
          label={t("settings.currencies.newVersion.to")}
          required
          width="date"
        >
          {(control) => (
            <DateInput
              control={control}
              value={toText}
              onChange={setToText}
              onValue={setTo}
              invalid={error !== null}
            />
          )}
        </Field>
      </form>
    </Modal>
  );
}

/** SCREENS_B §9.4 "Submit for approval" confirmation. */
function SubmitVersionModal({
  set,
  version,
  rateCount,
  onClose,
}: {
  readonly set: FxRateSet;
  readonly version: FxRateSetVersion;
  readonly rateCount: number;
  readonly onClose: () => void;
}) {
  const toast = useToast();
  const submit = useCommand<FxRateSetVersion>({
    method: "POST",
    path: fxVersionCommandPath(version.id, "submit"),
    invalidates: [EVERY_FX_VERSION],
  });
  const params = { code: set.code, version: String(version.version_no) };
  return (
    <Modal
      open
      variant="confirmation"
      title={t("settings.currencies.submitDialog.title", {
        ...params,
        formatted: formatNumber(rateCount, { kind: "count" }),
      })}
      description={t("settings.currencies.submitDialog.description")}
      primaryAction={{
        label: t("settings.currencies.submitDialog.confirm"),
        onAction: () => {
          void (async () => {
            const outcome = await submit.submit({});
            if (outcome.kind === "succeeded") {
              toast.show({
                tone: "positive",
                message: t("settings.currencies.submitDialog.submitted", params),
              });
              onClose();
            }
          })();
        },
      }}
      submitting={submit.pending}
      onClose={onClose}
      testId="SF-15-dialog-submit-version"
    >
      <RefusalBanner problem={submit.problem} />
    </Modal>
  );
}
