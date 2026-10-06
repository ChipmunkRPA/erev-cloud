// SF-05:reconciliations Reconciliations (SCREENS_B §2.1; §0.3 SB-R-06; §0.4 E-59; §1 route tabs; SCREENS
// RT-102, SCR-PERM-02, SCR-PERM-03, SCR-ST-03, SCR-ST-05, SCR-ST-12; DESIGN_SYSTEM DS-CMP-10, DS-CMP-19,
// DS-CMP-24, DS-CMP-28; 04 API-R-40 §16.8, T-CLS-06; PRD SM-09, J-13.10, J-13.11; supervisor ruling R-54
// (a), (b); BUILD_SPEC CLO-25, CLO-17). The Reconciliations tab of the close cockpit: the current
// reconciliation of each kind with its E-59 chip, variances and sign-offs, and "Generate reconciliation",
// which starts a `RECONCILIATION_GENERATE` job and follows it in place. Every generation is a new
// reconciliation: the grid lists the rows of `is_current=true`, and the generations they replaced
// (`is_current=false`) stay reachable below it as history. A generated subledger-to-GL reconciliation
// opens where its trial balance is attached. The labels and chips of E-58 and E-59 are shared with
// SF-05:reconciliation.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useId, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { Link, useNavigate } from "react-router";

import { DataGrid } from "../../components/data-grid/DataGrid";
import {
  type GridColumn,
  type GridColumnState,
  type GridSource,
  initialColumnState,
} from "../../components/data-grid/types";
import { EmptyState } from "../../components/feedback/EmptyState";
import { JobProgress } from "../../components/feedback/JobProgress";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { useToast } from "../../components/feedback/Toast";
import { CaretDown, CaretRight, Plus } from "../../components/icons/registry";
import { Money } from "../../components/money/Money";
import { NoValue } from "../../components/money/Num";
import { Button } from "../../components/ui/Button";
import { Menu, type MenuItem } from "../../components/ui/Menu";
import { chipFor, StatusChip } from "../../components/ui/StatusChip";
import { useCommand } from "../../lib/api/commands";
import { isTerminal, useJob } from "../../lib/api/jobs";
import { currencyRegistered } from "../../lib/api/queries/approvals";
import { EVERY_PERIOD } from "../../lib/api/queries/periods";
import {
  EVERY_RECONCILIATION,
  fetchPeriodReconciliations,
  fetchReconciliation,
  GENERATED_KINDS,
  periodIsWorkable,
  RECON_PREPARE_PERMISSION,
  type Reconciliation,
  type ReconciliationCreateIn,
  RECONCILIATION_ID_HEADER,
  RECONCILIATION_KINDS,
  reconciliationIdOf,
  type ReconciliationKind,
  reconciliationKey,
  type ReconciliationOut,
  reconciliationRoute,
  RECONCILIATIONS_PATH,
  type ReconciliationScope,
  reconciliationsKey,
  signoffsOf,
} from "../../lib/api/queries/reconciliations";
import { periodLabel } from "../../lib/api/queries/tenant";
import { queryKey } from "../../lib/api/query-keys";
import { formatNumber, formatTimestamp } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { type CockpitContext, CockpitFrame, Mono } from "./cockpit";

/** SCREENS_B §2.1 wireframes: Preparer and Reviewer are two columns from 1440 px, one below. */
const WIDE_VIEWPORT_PX = 1440;
/**
 * SCREENS_B §2.1: the columns neither wireframe shows stay in the column chooser, so the six columns
 * of the 1440 px wireframe fit beside the expanded rail without clipping (DS-AP-10).
 */
const HIDDEN_COLUMNS: readonly string[] = ["unexplained_other", "certified_at", "report_run"];
const CELL = "px-3 py-2 text-body-sm";

// ---------------------------------------------------------------------------------------------------
// Labels and chips shared by the SF-05 reconciliation screens.

/** SCREENS_B §1.1: the E-58 label of a reconciliation kind. */
export function kindLabel(kind: ReconciliationKind): string {
  return t(`close.reconciliations.kind.${kind}`);
}

/** SCREENS_B §0.4: the second chip Difference, while variances exist and the row is not certified. */
export function hasDifference(
  reconciliation: Pick<ReconciliationOut, "variance_count" | "status">,
): boolean {
  return reconciliation.variance_count > 0 && reconciliation.status !== "CERTIFIED";
}

export interface ReconciliationChipsProps {
  readonly reconciliation: Pick<
    ReconciliationOut,
    "status" | "variance_count" | "auto_certify_rule"
  >;
  /** A generation a later one replaced also reads Superseded ([J] CLO-25; supervisor ruling R-54 (b)). */
  readonly superseded?: boolean;
}

/** The E-59 chip, its "under <rule key> v<n>" caption, and the Difference and Superseded chips. */
export function ReconciliationChips({
  reconciliation,
  superseded = false,
}: ReconciliationChipsProps) {
  const chip = chipFor("E-59", reconciliation.status);
  const rule = reconciliation.auto_certify_rule;
  const caption =
    reconciliation.status === "AUTO_CERTIFIED" && rule !== null
      ? t("close.reconciliations.ruleCaption", { rule: rule.rule_key, version: rule.version_no })
      : null;
  return (
    <span className="inline-flex items-center gap-1.5">
      {chip === null ? null : <StatusChip status={chip.status} caption={caption} />}
      {hasDifference(reconciliation) ? <StatusChip status="Difference" /> : null}
      {superseded ? <StatusChip status="Superseded" /> : null}
    </span>
  );
}

/**
 * The signer of a role as the grids and the sign-off region name it: the latest sign-off of the role,
 * "System" for the preparer of an auto-certified reconciliation, else null (SCREENS_B §2.1).
 */
export function signerName(
  reconciliation: Pick<ReconciliationOut, "signoffs" | "auto_certify_rule">,
  role: "PREPARER" | "REVIEWER",
): string | null {
  const signed = signoffsOf(reconciliation, role).at(-1);
  if (signed !== undefined) {
    return signed.signer.display_name;
  }
  return role === "PREPARER" && reconciliation.auto_certify_rule !== null
    ? t("close.reconciliations.system")
    : null;
}

/** A money cell; an amount whose currency is not registered shows no value (DS-FMT-03). */
export function MoneyCell({
  value,
  currency,
}: {
  readonly value: string | null;
  readonly currency: string;
}) {
  return value === null || !currencyRegistered(currency) ? (
    <NoValue />
  ) : (
    <Money value={value} currency={currency} variant="cell" />
  );
}

function subscribeToResize(onChange: () => void): () => void {
  window.addEventListener("resize", onChange);
  return () => {
    window.removeEventListener("resize", onChange);
  };
}

function useWideViewport(): boolean {
  return useSyncExternalStore(
    subscribeToResize,
    () => window.innerWidth >= WIDE_VIEWPORT_PX,
    () => true,
  );
}

/** The current reconciliation of each kind, in E-58 order (04 T-CLS-06 "Current reconciliation"). */
function byKind(current: readonly Reconciliation[]): readonly Reconciliation[] {
  return [...current].sort(
    (left, right) =>
      RECONCILIATION_KINDS.indexOf(left.kind) - RECONCILIATION_KINDS.indexOf(right.kind),
  );
}

// ---------------------------------------------------------------------------------------------------
// The Reconciliations tab.

export function ReconciliationsPage() {
  return (
    <CockpitFrame tab="reconciliations">
      {(context) => <ReconciliationsTab {...context} />}
    </CockpitFrame>
  );
}

/** A generation this page started: its job, and the reconciliation the 202 named. */
interface Generation {
  readonly jobId: string;
  readonly kind: ReconciliationKind;
  readonly reconciliationId: string | null;
}

interface ColumnSources {
  readonly scope: ReconciliationScope;
  readonly ctxSearch: string;
  /** The entity's functional currency, which `unexplained_other_amount` is in (04 T-CLS-06). */
  readonly functional: string;
  readonly wide: boolean;
  readonly onOpen: (row: Reconciliation) => void;
}

function listColumns({
  scope,
  ctxSearch,
  functional,
  wide,
  onOpen,
}: ColumnSources): readonly GridColumn<Reconciliation>[] {
  const href = (row: Reconciliation) => `${reconciliationRoute(scope, row.id)}${ctxSearch}`;
  const signers: readonly GridColumn<Reconciliation>[] = wide
    ? [
        {
          id: "preparer",
          header: t("close.reconciliations.column.preparer"),
          kind: "user",
          value: (row) => signerName(row, "PREPARER"),
          width: 176,
        },
        {
          id: "reviewer",
          header: t("close.reconciliations.column.reviewer"),
          kind: "user",
          value: (row) => signerName(row, "REVIEWER"),
          width: 176,
        },
      ]
    : [
        {
          // SCREENS_B §2.1, 1280 px: "<preparer> · <reviewer>" in one column.
          id: "signoffs",
          header: t("close.reconciliations.column.signoffs"),
          kind: "text",
          value: (row) =>
            signerName(row, "PREPARER") === null && signerName(row, "REVIEWER") === null
              ? null
              : `${signerName(row, "PREPARER") ?? ""} · ${signerName(row, "REVIEWER") ?? ""}`,
          render: (row) => (
            <span className="flex min-w-0 items-center gap-1.5">
              <span className="truncate">{signerName(row, "PREPARER") ?? <NoValue />}</span>
              <span aria-hidden="true" className="text-fg-3">
                ·
              </span>
              <span className="truncate">{signerName(row, "REVIEWER") ?? <NoValue />}</span>
            </span>
          ),
          width: 272,
        },
      ];
  return [
    {
      id: "number",
      header: t("close.reconciliations.column.number"),
      kind: "identifier",
      value: (row) => row.reconciliation_no,
      href,
      width: 128,
    },
    {
      id: "kind",
      header: t("close.reconciliations.column.kind"),
      kind: "text",
      value: (row) => kindLabel(row.kind),
      width: 232,
    },
    {
      id: "status",
      header: t("close.reconciliations.column.status"),
      kind: "status",
      value: (row) => row.status,
      render: (row) => <ReconciliationChips reconciliation={row} />,
      width: 320,
    },
    {
      id: "variances",
      header: t("close.reconciliations.column.variances"),
      kind: "number",
      numberKind: "count",
      value: (row) => String(row.variance_count),
      render: (row) => (
        <Link to={href(row)} tabIndex={-1} className="num text-accent-fg hover:underline">
          {formatNumber(row.variance_count, { kind: "count" })}
        </Link>
      ),
      activate: onOpen,
      width: 120,
    },
    {
      id: "unexplained_other",
      header: t("close.reconciliations.column.unexplainedOther", { currency: functional }),
      kind: "money",
      value: (row) => row.unexplained_other_amount?.amount ?? null,
      currency: (row) => row.unexplained_other_amount?.currency ?? functional,
      render: (row) => (
        <MoneyCell
          value={row.unexplained_other_amount?.amount ?? null}
          currency={row.unexplained_other_amount?.currency ?? functional}
        />
      ),
      width: 232,
    },
    ...signers,
    {
      id: "certified_at",
      header: t("close.reconciliations.column.certified"),
      kind: "timestamp",
      value: (row) => row.certified_at,
      width: 192,
    },
    {
      // SF-08:run is not built, so the run number is text (XR-14).
      id: "report_run",
      header: t("close.reconciliations.column.reportRun"),
      kind: "text",
      value: (row) => row.report_run_no,
      render: (row) =>
        row.report_run_no === null ? <NoValue /> : <Mono>{row.report_run_no}</Mono>,
      width: 136,
    },
  ];
}

function ReconciliationsTab({ cockpit, permissions, ctxSearch }: CockpitContext) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const wide = useWideViewport();
  const period = cockpit.period;
  const entity = period.entity.code;
  const book = period.book;
  const periodKey = period.period.period_key;
  const scope = useMemo<ReconciliationScope>(
    () => ({ entity, book, period: periodKey }),
    [entity, book, periodKey],
  );
  const label = periodLabel(period.period);
  const functional = cockpit.journal_preview.debit_functional.currency;
  // SCR-PERM-02 and SCR-PERM-03: the control needs `recon.prepare`, and a period that is not open, in
  // soft close or reopened generates nothing (PRD SM-09), so it is not rendered there.
  const canGenerate =
    permissions.includes(RECON_PREPARE_PERMISSION) && periodIsWorkable(period.state);

  // The generations a later one replaced (`is_current=false`), for "Earlier generations".
  const earlier = useQuery({
    queryKey: reconciliationsKey(scope, false),
    queryFn: () => fetchPeriodReconciliations(scope, false),
  });
  const superseded = earlier.data ?? [];

  const [started, setStarted] = useState<readonly Generation[]>([]);
  const command = useCommand({
    method: "POST",
    path: RECONCILIATIONS_PATH,
    invalidates: [EVERY_RECONCILIATION, EVERY_PERIOD],
  });
  const generate = async (kind: ReconciliationKind, replaces: string | null = null) => {
    const outcome = await command.submit({
      kind,
      entity_code: entity,
      book,
      period_key: periodKey,
    } satisfies ReconciliationCreateIn);
    if (outcome.kind !== "accepted") {
      return;
    }
    const generation: Generation = {
      jobId: outcome.jobId,
      kind,
      reconciliationId: outcome.response.headers.get(RECONCILIATION_ID_HEADER),
    };
    setStarted((previous) => [...previous.filter((item) => item.jobId !== replaces), generation]);
  };

  const source: GridSource<Reconciliation> = useMemo(
    () => ({
      queryKey: queryKey("reconciliations", "tenant", { ...scope, view: "current-grid" }),
      // One current reconciliation per kind (`is_current=true`): the grid shows them as one page.
      fetchPage: async () => {
        const current = byKind(
          await queryClient.fetchQuery({
            queryKey: reconciliationsKey(scope, true),
            queryFn: () => fetchPeriodReconciliations(scope, true),
          }),
        );
        return {
          items: current,
          nextCursor: null,
          total: { count: current.length, capped: false },
        };
      },
    }),
    [queryClient, scope],
  );
  const columns = useMemo(
    () =>
      listColumns({
        scope,
        ctxSearch,
        functional,
        wide,
        onOpen: (row) => void navigate(`${reconciliationRoute(scope, row.id)}${ctxSearch}`),
      }),
    [scope, ctxSearch, functional, wide, navigate],
  );
  const defaultColumns = useMemo(
    (): GridColumnState => initialColumnState(columns, HIDDEN_COLUMNS),
    [columns],
  );

  const menu = (align: "start" | "end") =>
    canGenerate ? <GenerateMenu align={align} onGenerate={(kind) => void generate(kind)} /> : null;

  return (
    <div className="flex flex-col gap-4">
      <RefusalBanner problem={command.problem} />
      {started.map((generation) => (
        <GenerationProgress
          key={generation.jobId}
          generation={generation}
          onRetry={() => void generate(generation.kind, generation.jobId)}
          onOpen={(id) => void navigate(`${reconciliationRoute(scope, id)}${ctxSearch}`)}
        />
      ))}
      <div className="flex min-h-48 flex-col">
        <DataGrid<Reconciliation>
          // The column set follows the viewport, and the grid holds its own column state.
          key={wide ? "wide" : "narrow"}
          name="reconciliations"
          title={t("close.reconciliations.title")}
          errorTitle={t("close.reconciliations.loadError")}
          // SCREENS_B §2.1 heading "Reconciliations · <period label>": one row per required kind, so
          // the toolbar names the period where other grids count rows.
          countLabel={() => label}
          columns={columns}
          source={source}
          rowKey={(row) => row.id}
          rowLabel={(row) => row.reconciliation_no}
          rowHref={(row) => `${reconciliationRoute(scope, row.id)}${ctxSearch}`}
          testIdPrefix="SF-05"
          rowTestKey={(row) => row.kind}
          defaultColumnState={defaultColumns}
          toolbarActions={menu("end")}
          emptyState={
            <div className="flex flex-col items-start gap-4">
              <EmptyState
                title={t("close.reconciliations.emptyTitle", { period: label })}
                description={t("close.reconciliations.emptyDescription")}
                headingLevel={3}
              />
              {menu("start")}
            </div>
          }
        />
      </div>
      {superseded.length === 0 ? null : (
        <EarlierGenerations rows={superseded} scope={scope} ctxSearch={ctxSearch} />
      )}
    </div>
  );
}

/** DS-CMP-28 menu button "Generate reconciliation": the kinds the API generates on demand (XR-14). */
function GenerateMenu({
  align,
  onGenerate,
}: {
  readonly align: "start" | "end";
  readonly onGenerate: (kind: ReconciliationKind) => void;
}) {
  const items: MenuItem[] = GENERATED_KINDS.map((kind) => ({
    id: kind,
    label: kindLabel(kind),
    onSelect: () => onGenerate(kind),
  }));
  return (
    <Menu
      label={t("close.reconciliations.generate")}
      icon={Plus}
      variant="primary"
      align={align}
      items={items}
    />
  );
}

/**
 * SB-R-06 "Generating <kind label>" with the DS-CMP-24 indicator, then the toast that names the new
 * reconciliation, or the SCR-ST-12 banner with Retry. The generation is repeatable: every one is a new
 * reconciliation (04 T-CLS-06). A subledger-to-GL reconciliation has nothing to show before its trial
 * balance, so it opens in its "Attach trial balance" state in place of the toast (SCREENS_B §2.1).
 */
function GenerationProgress({
  generation,
  onRetry,
  onOpen,
}: {
  readonly generation: Generation;
  readonly onRetry: () => void;
  /** Opens SF-05:reconciliation of the reconciliation the job inserted. */
  readonly onOpen: (reconciliationId: string) => void;
}) {
  const job = useJob(generation.jobId);
  const toast = useToast();
  const queryClient = useQueryClient();
  const announced = useRef(false);
  const data = job.data;
  const kind = kindLabel(generation.kind);
  useEffect(() => {
    if (data === undefined || !isTerminal(data) || announced.current) {
      return;
    }
    announced.current = true;
    void queryClient.invalidateQueries({ queryKey: EVERY_RECONCILIATION });
    void queryClient.invalidateQueries({ queryKey: EVERY_PERIOD });
    if (data.state !== "SUCCEEDED" && data.state !== "SUCCEEDED_WITH_EXCEPTIONS") {
      return;
    }
    const id = generation.reconciliationId ?? reconciliationIdOf(data.result?.href);
    if (id === null) {
      return;
    }
    if (generation.kind === "SUBLEDGER_TO_GL") {
      onOpen(id);
      return;
    }
    void queryClient
      .fetchQuery({ queryKey: reconciliationKey(id), queryFn: () => fetchReconciliation(id) })
      .then(
        (created) => {
          toast.show({
            tone: "positive",
            message: t("close.reconciliations.generated", {
              number: created.reconciliation_no,
              kind,
            }),
          });
        },
        // The list shows the new reconciliation; without its number there is nothing to name.
        () => undefined,
      );
  });
  if (data === undefined || (isTerminal(data) && data.state !== "FAILED")) {
    return null;
  }
  return (
    <div
      data-testid="SF-05-job-reconciliations"
      className="rounded-md border border-hairline bg-surface px-[var(--panel-pad)] py-2"
    >
      <JobProgress
        label={t("close.reconciliations.generating", { kind })}
        job={data}
        unit={t("close.reconciliations.unit")}
        onRetry={data.state === "FAILED" ? onRetry : undefined}
      />
    </div>
  );
}

/**
 * The generations a later one replaced (supervisor ruling R-54 (b)): reachable, and plainly not
 * current. A disclosure under the grid, closed until asked for ([J] CLO-25).
 */
function EarlierGenerations({
  rows,
  scope,
  ctxSearch,
}: {
  readonly rows: readonly Reconciliation[];
  readonly scope: ReconciliationScope;
  readonly ctxSearch: string;
}) {
  const panelId = useId();
  const [open, setOpen] = useState(false);
  const label = t("close.reconciliations.earlier.toggle", {
    total: formatNumber(rows.length, { kind: "count" }),
  });
  const headers = ["number", "kind", "status", "variances", "generated"] as const;
  return (
    <section
      data-testid="SF-05-grid-reconciliation-history"
      className="rounded-md border border-hairline bg-surface"
    >
      <h2 className="px-1 py-1">
        <Button
          variant="ghost"
          icon={open ? CaretDown : CaretRight}
          aria-expanded={open}
          aria-controls={open ? panelId : undefined}
          onClick={() => setOpen((shown) => !shown)}
        >
          {label}
        </Button>
      </h2>
      {open ? (
        <div id={panelId} className="flex flex-col gap-2 border-t border-hairline pt-2">
          <p className="px-3 text-body-sm text-fg-2">{t("close.reconciliations.earlier.note")}</p>
          <div className="overflow-x-auto">
            <table aria-label={label} className="w-full border-collapse">
              <thead>
                <tr className="border-b border-hairline">
                  {headers.map((id) => (
                    <th
                      key={id}
                      scope="col"
                      className={`${CELL} ${id === "variances" ? "text-end" : "text-start"} text-caption text-fg-3`}
                    >
                      {t(`close.reconciliations.column.${id}`)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className="border-b border-hairline last:border-b-0">
                    <th scope="row" className={`${CELL} text-start font-normal`}>
                      <Link
                        to={`${reconciliationRoute(scope, row.id)}${ctxSearch}`}
                        className="font-mono text-mono-sm text-accent-fg hover:underline"
                      >
                        {row.reconciliation_no}
                      </Link>
                    </th>
                    <td className={`${CELL} text-fg-1`}>{kindLabel(row.kind)}</td>
                    <td className={CELL}>
                      <ReconciliationChips reconciliation={row} />
                    </td>
                    <td className={`${CELL} num text-end text-fg-1`}>
                      {formatNumber(row.variance_count, { kind: "count" })}
                    </td>
                    <td className={`${CELL} num whitespace-nowrap text-fg-2`}>
                      <span data-volatile="">{formatTimestamp(row.created_at)}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}
    </section>
  );
}
