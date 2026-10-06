// SF-05:reconciliation Reconciliation detail (SCREENS_B §2.2; §0.3 SB-R-05; §0.4 E-59 and the "High
// risk" classification; SCREENS RT-103, SCR-PERM-02, SCR-PERM-03, SCR-PERM-05, SCR-ST-05, SCR-ST-07;
// DESIGN_SYSTEM DS-CMP-06, DS-CMP-09 to DS-CMP-11, DS-CMP-19, DS-CMP-21, DS-CMP-29, DS-FMT-12, DS-FMT-17,
// DS-FMT-30; 04 API-R-40 §16.8, T-CLS-06 to T-CLS-08; PRD SM-09, ACT-33, ACT-34, ACT-45, SoD-7, J-13.11,
// J-13.12, J-23.9; supervisor rulings R-54 (b), (c), R-68 (c); BUILD_SPEC CLO-25, CLO-17). One
// reconciliation: totals by account and currency, the itemised differences with their classification and
// explanation, and the preparer's and the reviewer's sign-offs. A subledger-to-GL reconciliation first
// takes its trial balance — pulled through a GL connection or uploaded — and every reader follows that
// request on the record itself. Explanations change while the reconciliation is a draft; the preparer
// signs in an MFA-verified session and the reviewer with a step-up (SCR-PERM-05: the command is sent
// again with the same Idempotency-Key). A reconciliation a later generation replaced, a certified one
// and one whose period is not open are read-only, and a refusal of the API is shown on the page and
// followed by a fresh read, so a row replaced meanwhile leads to the current one. Every figure is an API
// string (DG-FE-08): the key figures are the server's `summary`, never summed here.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  type DragEvent,
  type ReactNode,
  useCallback,
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
} from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";

import { MFA_ENROL_PATH } from "../../app/auth/MfaGate";
import { contextSearch } from "../../app/shell/IconRail";
import { DataGrid } from "../../components/data-grid/DataGrid";
import {
  type GridColumn,
  type GridColumnState,
  type GridSource,
  initialColumnState,
} from "../../components/data-grid/types";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { JobProgress } from "../../components/feedback/JobProgress";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { ReasonField, reasonError } from "../../components/form/ReasonField";
import { DotsThree, UploadSimple } from "../../components/icons/registry";
import { NoValue } from "../../components/money/Num";
import { type MetaItem, RecordHeader } from "../../components/record/RecordHeader";
import { Button } from "../../components/ui/Button";
import { cn } from "../../components/ui/cn";
import { Drawer } from "../../components/ui/Drawer";
import { Menu, type MenuItem } from "../../components/ui/Menu";
import { Modal } from "../../components/ui/Modal";
import { SegmentedControl, type SegmentOption } from "../../components/ui/SegmentedControl";
import { OutlineChip, StatusChip } from "../../components/ui/StatusChip";
import {
  type CommandOutcome,
  type CommandState,
  useCommand,
  useCommandKeys,
} from "../../lib/api/commands";
import { JOB_POLL_INTERVAL_MS } from "../../lib/api/jobs";
import { ApiProblem } from "../../lib/api/problems";
import { currencyRegistered } from "../../lib/api/queries/approvals";
import { IMPORT_UPLOAD_PERMISSION } from "../../lib/api/queries/imports";
import { type Me, useMe } from "../../lib/api/queries/me";
import { EVERY_PERIOD } from "../../lib/api/queries/periods";
import {
  EVERY_RECONCILIATION,
  fetchPeriodReconciliations,
  fetchReconciliation,
  fetchReconciliationItems,
  INTEGRATION_MANAGE_PERMISSION,
  isZeroAmount,
  needsExplanation,
  periodIsWorkable,
  RECON_PREPARE_PERMISSION,
  RECON_SIGNOFF_PERMISSION,
  type Reconciliation,
  type ReconciliationAttachIn,
  type ReconciliationItem,
  reconciliationItemsKey,
  type ReconciliationItemUpdateIn,
  reconciliationKey,
  type ReconciliationOut,
  type ReconciliationReopenIn,
  reconciliationRoute,
  RECONCILIATIONS_PATH,
  reconciliationsKey,
  reconciliationsRoute,
  type ReconciliationSignIn,
  type ReconciliationSummary,
  type ReconciliationTotal,
  scopeOf,
  signoffsOf,
  type TrialBalanceState,
  trialBalanceState,
} from "../../lib/api/queries/reconciliations";
import { uploadFile } from "../../lib/api/queries/ssp-books";
import { fetchPeriods, periodLabel, periodsKey, rowIfMatch } from "../../lib/api/queries/tenant";
import { queryKey, type QueryKey } from "../../lib/api/query-keys";
import { LISTED_BY_THE_SCREEN, placeProblem } from "../../lib/api/refusals";
import { formatMoney, formatNumber, formatTimestamp, NBSP, NO_VALUE } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { SelectField } from "../contracts/drawers/common";
import { useBuiltPaths } from "../settings/index";
import { StepUpModal } from "../settings/profile";
import { bookLabel, CLOSE_PATH, cockpitRoute, Mono, RetryBanner, useCloseContext } from "./cockpit";
import { kindLabel, MoneyCell, ReconciliationChips } from "./reconciliations";

/** SCREENS SCR-URL-01 to SCR-URL-03: the context a close link keeps. */
const CONTEXT = ["entity", "period", "book"] as const;
/** SCREENS RT-10, the target of a difference's contract. */
const CONTRACT_ROUTE = "/contracts/:contractId";
/** The reads a reconciliation command changes: the record, the period's list and the cockpit. */
const COMMAND_KEYS: readonly QueryKey[] = [EVERY_RECONCILIATION, EVERY_PERIOD];
const CELL = "px-3 py-2 text-body-sm";

type SignAction = "prepare" | "review";

/** SCREENS_B §2.2: the invoice number of a billing difference or the GL document of a ledger one. */
export function itemReference(
  item: Pick<ReconciliationItem, "invoice_number" | "gl_document_reference">,
): string | null {
  return item.invoice_number ?? item.gl_document_reference;
}

function itemKindLabel(item: Pick<ReconciliationItem, "item_kind">): string {
  return t(`close.reconciliation.itemKind.${item.item_kind}`);
}

/** SCREENS_B §2.2 "<source label>": GL, Billing or Rollforward by kind. */
function sourceLabel(reconciliation: Pick<ReconciliationOut, "kind">): string {
  return t(`close.reconciliation.sourceLabel.${reconciliation.kind}`);
}

/** The distinct currencies of the totals, then of the differences, in the order they appear. */
function currenciesOf(
  totals: readonly ReconciliationTotal[],
  items: readonly ReconciliationItem[],
): readonly string[] {
  return [
    ...new Set([...totals.map((total) => total.currency), ...items.map((item) => item.currency)]),
  ];
}

/** DS-FMT-12: `<Label> (<ISO>)` in a single-currency grid, the bare label beside a Currency column. */
function amountHeader(name: "subledger" | "source" | "difference", currency: string | null) {
  return currency === null
    ? t(`close.reconciliation.amount.${name}`)
    : t(`close.reconciliation.amount.${name}In`, { currency });
}

/** SCREENS_B §2.2 SCR-ST-07 "Reconciliation not found" with "Go to Close". */
function ReconciliationNotFound() {
  const navigate = useNavigate();
  const location = useLocation();
  return (
    <div data-testid="SF-05-page">
      <EmptyState
        title={t("close.reconciliation.notFound.title")}
        description={t("close.reconciliation.notFound.description")}
        headingLevel={2}
        action={{
          label: t("close.reconciliation.notFound.action"),
          onAction: () => void navigate(`${CLOSE_PATH}${contextSearch(location.search, CONTEXT)}`),
        }}
      />
    </div>
  );
}

export function ReconciliationPage() {
  const { entity = "", book = "", period = "", reconciliationId = "" } = useParams();
  useCloseContext(entity, book, period);
  const me = useMe();
  const record = useQuery({
    queryKey: reconciliationKey(reconciliationId),
    queryFn: () => fetchReconciliation(reconciliationId),
    // A refusal (404 for an id outside the caller's entities, REQ-PLT-012) is an answer, not an outage.
    retry: (failures, error) =>
      failures < 1 && !(error instanceof ApiProblem && error.status >= 400 && error.status < 500),
    // A trial balance being attached is followed on the record itself, which every reader may read
    // (the job is read by its initiator only).
    refetchInterval: (query) =>
      trialBalanceState(query.state.data) === "attaching" ? JOB_POLL_INTERVAL_MS : false,
  });

  if (me.error !== null) {
    return <Banner tone="negative" title={me.error.message} />;
  }
  if (record.error !== null) {
    return record.error instanceof ApiProblem && record.error.status === 404 ? (
      <ReconciliationNotFound />
    ) : (
      <RetryBanner
        title={t("close.reconciliation.loadError")}
        problem={record.error}
        onRetry={() => void record.refetch()}
      />
    );
  }
  if (me.data === undefined || record.data === undefined) {
    return (
      <div data-testid="SF-05-page">
        <Skeleton region={t("close.reconciliation.region")} shape="rows" count={8} />
      </div>
    );
  }
  // The path names the reconciliation's own entity, book and period (RT-103); another is no such record.
  const own = scopeOf(record.data);
  if (own.entity !== entity || own.book !== book || own.period !== period) {
    return <ReconciliationNotFound />;
  }
  return <ReconciliationView key={record.data.id} reconciliation={record.data} me={me.data} />;
}

interface ReconciliationViewProps {
  readonly reconciliation: Reconciliation;
  readonly me: Me;
}

function ReconciliationView({ reconciliation, me }: ReconciliationViewProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const built = useBuiltPaths();
  const ctxSearch = contextSearch(location.search, CONTEXT);
  const id = reconciliation.id;
  const number = reconciliation.reconciliation_no;
  const status = reconciliation.status;
  const kind = kindLabel(reconciliation.kind);
  const label = periodLabel(reconciliation.period);
  const entity = reconciliation.entity.code;
  const book = reconciliation.book;
  const periodKey = reconciliation.period.period_key;
  const scope = useMemo(() => ({ entity, book, period: periodKey }), [entity, book, periodKey]);
  const title = `${number} · ${kind} · ${label}`;
  const permissions = me.permissions;

  const [dialog, setDialog] = useState<SignAction | "reopen" | null>(null);
  const [stepUp, setStepUp] = useState<SignAction | null>(null);
  const [explained, setExplained] = useState<string | null>(null);
  const [refusal, setRefusal] = useState<ApiProblem | null>(null);
  const [unsent, setUnsent] = useState(false);
  const [unexplainedShown, setUnexplainedShown] = useState(false);
  const [signedNow, setSignedNow] = useState(false);

  // The period state decides whether any command is admitted (PRD SM-09); the context pill reads the
  // same list, so this is its cached read.
  const periodQuery = { entity, book };
  const periods = useQuery({
    queryKey: periodsKey(periodQuery),
    queryFn: () => fetchPeriods(periodQuery),
  });
  const periodState =
    periods.data?.find((item) => item.period.period_key === periodKey)?.state ?? null;
  // A failed read leaves the state unknown: the API stays the enforcer.
  const workable = periods.isError || periodIsWorkable(periodState);

  // A subledger-to-GL reconciliation compares nothing before its trial balance is attached, so it has
  // no differences to read; they are read once it has its source, and so never from before it.
  const trialBalance = trialBalanceState(reconciliation);
  const awaitsSource =
    trialBalance === "missing" || trialBalance === "attaching" || trialBalance === "failed";
  const items = useQuery({
    queryKey: reconciliationItemsKey(id),
    queryFn: () => fetchReconciliationItems(id),
    enabled: !awaitsSource,
  });
  // A replaced reconciliation names the current one of its kind (supervisor ruling R-54 (b)).
  const generations = useQuery({
    queryKey: reconciliationsKey(scope, true),
    queryFn: () => fetchPeriodReconciliations(scope, true),
    enabled: !reconciliation.is_current,
  });
  const current =
    generations.data?.find((item) => item.is_current && item.kind === reconciliation.kind) ?? null;

  const prepare = useCommand<ReconciliationOut>({
    method: "POST",
    path: `${RECONCILIATIONS_PATH}/${id}/prepare`,
    invalidates: COMMAND_KEYS,
  });
  const review = useCommand<ReconciliationOut>({
    method: "POST",
    path: `${RECONCILIATIONS_PATH}/${id}/sign`,
    invalidates: COMMAND_KEYS,
  });
  const reopen = useCommand<ReconciliationOut>({
    method: "POST",
    path: `${RECONCILIATIONS_PATH}/${id}/reopen`,
    invalidates: COMMAND_KEYS,
  });

  // SCR-PERM-02: a control renders only for a holder of its permission; SCR-PERM-03: and only in a
  // state that admits the command, so a read-only reconciliation shows none.
  const canPrepare = permissions.includes(RECON_PREPARE_PERMISSION);
  const canSignoff = permissions.includes(RECON_SIGNOFF_PERMISSION);
  // SoD-7: the reviewer's sign-off of a holder of `integration.manage` answers 403 (04 §16.8).
  const managesIntegrations = permissions.includes(INTEGRATION_MANAGE_PERMISSION);
  const live = reconciliation.is_current && workable && !periods.isPending;
  const preparedByViewer = signoffsOf(reconciliation, "PREPARER").some(
    (signoff) => signoff.signer.id === me.user.id,
  );
  const editable = live && status === "DRAFT" && canPrepare && !awaitsSource;
  // `attach-trial-balance` takes `recon.prepare` on a current draft (04 §16.8); a request that failed
  // wrote no source, so another may follow it.
  const mayAttach =
    live &&
    status === "DRAFT" &&
    canPrepare &&
    (trialBalance === "missing" || trialBalance === "failed");
  // An attach that ended changed the period's list and the cockpit's gate.
  const lastTrialBalance = useRef(trialBalance);
  useEffect(() => {
    const before = lastTrialBalance.current;
    lastTrialBalance.current = trialBalance;
    if (before === "attaching" && trialBalance !== "attaching") {
      void Promise.all(COMMAND_KEYS.map((key) => queryClient.invalidateQueries({ queryKey: key })));
    }
  }, [trialBalance, queryClient]);
  const mayReview =
    live && status === "PREPARED" && canSignoff && !managesIntegrations && !preparedByViewer;
  const mayReopen = live && (status === "PREPARED" || status === "REVIEWED") && canSignoff;

  const differences = items.data?.items ?? [];
  const unexplained = differences.filter(needsExplanation).length;
  const explainedItem =
    explained === null ? null : (differences.find((item) => item.id === explained) ?? null);

  /** A refusal that is about the record: shown on the page, and the record is read again. */
  const refuse = (problem: ApiProblem) => {
    setDialog(null);
    setExplained(null);
    setRefusal(problem);
    void Promise.all(COMMAND_KEYS.map((key) => queryClient.invalidateQueries({ queryKey: key })));
  };

  const settle = (action: SignAction | "reopen", outcome: CommandOutcome<ReconciliationOut>) => {
    if (outcome.kind === "succeeded" || outcome.kind === "accepted") {
      setDialog(null);
      setStepUp(null);
      setSignedNow(action === "prepare");
      toast.show({
        tone: "positive",
        message: t(`close.reconciliation.${action}.done`, { number }),
      });
      return;
    }
    if (outcome.kind === "network-error") {
      setDialog(null);
      setStepUp(null);
      setUnsent(true);
      return;
    }
    const problem = outcome.problem;
    const verification =
      problem.slug === "mfa-step-up-required" ||
      (problem.slug === "mfa-required" && me.mfa.enrolled);
    if (verification && action !== "reopen") {
      // SCR-PERM-05: verify, then the same command again with the same Idempotency-Key.
      setDialog(null);
      setStepUp(action);
      return;
    }
    setStepUp(null);
    if (problem.slug === "mfa-required") {
      void navigate(MFA_ENROL_PATH);
    } else if (problem.status !== 422) {
      // 422 names a field of the open dialog, which shows it; every other refusal is the record's and
      // is shown on the page. A 403 is among them (§2.2 rev 1.85): it was a toast, and PRD ERR-01's
      // two sentences take three lines of the two a toast shows (DS-CMP-22). One that carries no
      // sentence of its own takes ERR-01's, which says what to do.
      refuse(
        problem.slug === "forbidden" && problem.detail === null
          ? new ApiProblem({ ...problem, detail: t("close.reconciliation.problem.forbidden") })
          : problem,
      );
    }
  };

  const clearMessages = useCallback(() => {
    setRefusal(null);
    setUnsent(false);
    setUnexplainedShown(false);
  }, []);
  const openExplain = useCallback(
    (item: ReconciliationItem) => {
      clearMessages();
      setExplained(item.id);
    },
    [clearMessages],
  );
  const sendPrepare = async () => settle("prepare", await prepare.submit());
  const sendReview = async () =>
    settle(
      "review",
      await review.submit({
        role: "REVIEWER",
        statement_accepted: true,
      } satisfies ReconciliationSignIn),
    );
  const sendReopen = async (reason: string) =>
    settle("reopen", await reopen.submit({ reason } satisfies ReconciliationReopenIn));

  const openPrepare = () => {
    clearMessages();
    // SM-09 and DS-CMP-21: the control stays enabled and reports what is missing.
    if (items.data !== undefined && !items.data.truncated && unexplained > 0) {
      setUnexplainedShown(true);
      return;
    }
    prepare.reset();
    setDialog("prepare");
  };

  let primary: ReactNode = null;
  if (editable) {
    primary = (
      <Button variant="primary" onClick={openPrepare}>
        {t("close.reconciliation.action.prepare")}
      </Button>
    );
  } else if (mayReview) {
    primary = (
      <Button
        variant="primary"
        onClick={() => {
          clearMessages();
          review.reset();
          setDialog("review");
        }}
      >
        {t("close.reconciliation.action.review")}
      </Button>
    );
  }
  const overflow: MenuItem[] = mayReopen
    ? [
        {
          id: "reopen",
          label: t("close.reconciliation.action.reopen"),
          destructive: true,
          onSelect: () => {
            clearMessages();
            reopen.reset();
            setDialog("reopen");
          },
        },
      ]
    : [];

  const listHref = `${reconciliationsRoute(scope)}${ctxSearch}`;
  const banners: ReactNode[] = [];
  if (refusal !== null) {
    banners.push(
      <div key="refused" data-testid="SF-05-banner-refused">
        <RefusalBanner problem={refusal} />
      </div>,
    );
  }
  if (unsent) {
    banners.push(
      <Banner
        key="unsent"
        tone="negative"
        announce="live"
        title={t("close.reconciliation.problem.network")}
      />,
    );
  }
  if (unexplainedShown && unexplained > 0) {
    banners.push(
      <div key="unexplained" data-testid="SF-05-banner-unexplained">
        <Banner
          tone="negative"
          announce="live"
          title={t("close.reconciliation.prepare.unexplained", { count: unexplained })}
        />
      </div>,
    );
  }
  if (!reconciliation.is_current) {
    // The banner waits for the read that names the current reconciliation, so its text does not change.
    if (!generations.isPending) {
      banners.push(
        <div key="superseded" data-testid="SF-05-banner-superseded">
          <Banner
            tone="info"
            announce="static"
            title={
              current === null
                ? t("close.reconciliation.banner.supersededUnnamed", { number })
                : t("close.reconciliation.banner.superseded", {
                    number,
                    later: current.reconciliation_no,
                  })
            }
            actions={
              current === null ? undefined : (
                <Link
                  to={`${reconciliationRoute(scope, current.id)}${ctxSearch}`}
                  className="text-body-sm text-accent-fg hover:underline"
                >
                  {t("close.reconciliation.banner.openCurrent", {
                    number: current.reconciliation_no,
                  })}
                </Link>
              )
            }
          />
        </div>,
      );
    }
  } else if (status === "CERTIFIED") {
    banners.push(
      <div key="certified" data-testid="SF-05-banner-certified">
        <Banner
          tone="info"
          announce="static"
          title={t("close.reconciliation.banner.certified", {
            at: formatTimestamp(reconciliation.certified_at),
          })}
        />
      </div>,
    );
  } else if (status === "REOPENED") {
    banners.push(
      <div key="reopened" data-testid="SF-05-banner-reopened">
        <Banner
          tone="warning"
          announce="static"
          title={t("close.reconciliation.banner.reopened", { number })}
          actions={
            <Link to={listHref} className="text-body-sm text-accent-fg hover:underline">
              {t("close.reconciliation.breadcrumb.reconciliations")}
            </Link>
          }
        />
      </div>,
    );
  } else if (status === "PREPARED") {
    banners.push(
      <div key="frozen" data-testid="SF-05-banner-frozen">
        <Banner
          tone="info"
          announce={signedNow ? "live" : "static"}
          title={t("close.reconciliation.banner.frozen")}
        />
      </div>,
    );
    if (preparedByViewer) {
      // DB-10: the preparer reads why no reviewer control is offered.
      banners.push(
        <p
          key="own-preparation"
          data-testid="SF-05-banner-own-preparation"
          className="text-body-sm text-fg-2"
        >
          {t("close.reconciliation.banner.ownPreparation")}
        </p>,
      );
    }
  }
  const signable = status === "DRAFT" || status === "PREPARED" || status === "REVIEWED";
  if (reconciliation.is_current && signable && !periods.isPending && !workable) {
    banners.push(
      <div key="period" data-testid="SF-05-banner-period">
        <Banner
          tone="info"
          announce="static"
          title={t("close.reconciliation.banner.periodNotWorkable", { period: label, entity })}
        />
      </div>,
    );
  }

  let source: ReactNode = NO_VALUE;
  if (reconciliation.kind === "BILLING_TO_SUBLEDGER") {
    source = (
      <span data-volatile="">
        {t("close.reconciliation.source.billing", {
          at: formatTimestamp(reconciliation.as_of_known_at),
        })}
      </span>
    );
  } else if (reconciliation.kind === "SUBLEDGER_TO_GL") {
    const request = reconciliation.trial_balance;
    if (awaitsSource) {
      source = t("close.reconciliation.source.none");
    } else if (request === null || request.attached_at === null) {
      // The record names no request: the API does not state where the trial balance came from.
      source = t("close.reconciliation.source.trialBalance");
    } else if (request.source === "ADAPTER" && request.integration_connection !== null) {
      source = (
        <span data-volatile="">
          {t("close.reconciliation.source.pulled", {
            connection: request.integration_connection.name,
            at: formatTimestamp(request.attached_at),
          })}
        </span>
      );
    } else if (request.source === "FILE" && request.file !== null) {
      source = (
        <span data-volatile="">
          {t("close.reconciliation.source.uploaded", {
            file: request.file.name,
            at: formatTimestamp(request.attached_at),
          })}
        </span>
      );
    } else {
      source = t("close.reconciliation.source.trialBalance");
    }
  }
  const meta: MetaItem[] = [
    { label: t("close.reconciliation.meta.source"), value: source },
    {
      // SF-08:run is not built, so the run number is text (XR-14).
      label: t("close.reconciliation.meta.reportRun"),
      value:
        reconciliation.report_run_no === null ? (
          NO_VALUE
        ) : (
          <Mono>{reconciliation.report_run_no}</Mono>
        ),
    },
  ];

  return (
    <div data-testid="SF-05-page" className="flex flex-col gap-4">
      <RecordHeader
        title={title}
        breadcrumb={[
          {
            label: t("close.reconciliation.breadcrumb.close"),
            to: `${CLOSE_PATH}${ctxSearch}`,
          },
          {
            label: `${entity} · ${bookLabel(book)}`,
            to: `${cockpitRoute(entity, book, periodKey)}${ctxSearch}`,
          },
          { label: t("close.reconciliation.breadcrumb.reconciliations"), to: listHref },
        ]}
        chips={
          <ReconciliationChips
            reconciliation={reconciliation}
            superseded={!reconciliation.is_current}
          />
        }
        actions={
          <>
            {/* RecordHeader shows `primaryAction` only in its condensed bar; the page row carries it here. */}
            {primary}
            {overflow.length === 0 ? null : (
              <Menu
                label={t("close.reconciliation.action.more")}
                icon={DotsThree}
                iconOnly
                variant="ghost"
                align="end"
                items={overflow}
              />
            )}
          </>
        }
        primaryAction={primary ?? undefined}
        meta={meta}
        banner={
          banners.length === 0 ? undefined : <div className="flex flex-col gap-2">{banners}</div>
        }
        kpis={<KeyFigures reconciliation={reconciliation} />}
      />
      {awaitsSource ? (
        <AttachTrialBalance
          // A new request or a new outcome starts the section afresh: a failed pull opens on the upload.
          key={`${reconciliation.trial_balance?.job.id ?? "none"}:${trialBalance}`}
          reconciliation={reconciliation}
          periodLabel={label}
          state={trialBalance}
          mayAttach={mayAttach}
          canUpload={permissions.includes(IMPORT_UPLOAD_PERMISSION)}
          onRefused={refuse}
        />
      ) : (
        <>
          <TotalsGrid reconciliation={reconciliation} periodLabel={label} />
          <DifferencesGrid
            reconciliation={reconciliation}
            editable={editable}
            ctxSearch={ctxSearch}
            contractsBuilt={built.has(CONTRACT_ROUTE)}
            onExplain={openExplain}
          />
        </>
      )}
      <Signoffs reconciliation={reconciliation} />
      {dialog === "prepare" ? (
        <SignDialog
          title={t("close.reconciliation.prepare.title", { number })}
          statement={t("close.reconciliation.prepare.statement")}
          action={t("close.reconciliation.action.prepare")}
          command={prepare}
          onSign={() => void sendPrepare()}
          onClose={() => setDialog(null)}
        />
      ) : null}
      {dialog === "review" ? (
        <SignDialog
          title={t("close.reconciliation.review.title", { number })}
          statement={t("close.reconciliation.review.statement")}
          action={t("close.reconciliation.action.review")}
          command={review}
          onSign={() => void sendReview()}
          onClose={() => setDialog(null)}
        />
      ) : null}
      {dialog === "reopen" ? (
        <ReopenDialog
          number={number}
          command={reopen}
          onReopen={(reason) => void sendReopen(reason)}
          onClose={() => setDialog(null)}
        />
      ) : null}
      {stepUp === null ? null : (
        <StepUpModal
          onCancel={() => setStepUp(null)}
          onVerified={() => {
            const action = stepUp;
            setStepUp(null);
            void (action === "prepare" ? sendPrepare() : sendReview());
          }}
        />
      )}
      {explainedItem === null ? null : (
        <ExplainDrawer
          key={explainedItem.id}
          reconciliation={reconciliation}
          item={explainedItem}
          editable={editable}
          onRefused={refuse}
          onClose={() => setExplained(null)}
        />
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------
// Attach trial balance (subledger to GL; SCREENS_B §2.2 "Attach trial balance" and "States").

/** DS-CMP-31 holds five segments: up to four connections and "Upload CSV". */
const MAX_CONNECTION_SEGMENTS = 4;
const UPLOAD_MODE = "upload";
const CONNECTION_MODE = "connection";
/** 04 T-PLT-29: the purpose of an uploaded trial balance, and the files it takes (ERR-37). */
const TRIAL_BALANCE_PURPOSE = "IMPORT_SOURCE";
const TRIAL_BALANCE_FILES = ".csv,.xlsx";

interface AttachTrialBalanceProps {
  readonly reconciliation: Reconciliation;
  readonly periodLabel: string;
  readonly state: TrialBalanceState;
  /** `recon.prepare` on a current draft of a workable period (SCR-PERM-02, SCR-PERM-03). */
  readonly mayAttach: boolean;
  /** `import.upload`: the permission of `POST /files` purpose `IMPORT_SOURCE` (04 API-R-12). */
  readonly canUpload: boolean;
  /** A refusal that is about the record (409): the page shows it and reads the record again. */
  readonly onRefused: (problem: ApiProblem) => void;
}

/**
 * The state of a subledger-to-GL reconciliation without its source: the request being attached
 * (DS-CMP-24, followed on the record), the request that failed, and for the preparer the two ways to
 * attach — pull through a GL connection, or upload a file of account balances. The source is written
 * once (04 T-CLS-06), so the upload is sent by its own button, not by choosing the file.
 */
function AttachTrialBalance({
  reconciliation,
  periodLabel: label,
  state,
  mayAttach,
  canUpload,
  onRefused,
}: AttachTrialBalanceProps) {
  const queryClient = useQueryClient();
  const id = reconciliation.id;
  const entity = reconciliation.entity.code;
  const request = reconciliation.trial_balance;
  const connections = reconciliation.gl_connections;
  const failed = state === "failed" && request !== null ? request : null;
  const segmented = connections.length <= MAX_CONNECTION_SEGMENTS;
  const firstPull = segmented ? (connections[0]?.id ?? UPLOAD_MODE) : CONNECTION_MODE;
  // "Upload a CSV instead": after a failed pull, and where no connection exists.
  const [mode, setMode] = useState<string>(
    canUpload && failed?.source === "ADAPTER" ? UPLOAD_MODE : firstPull,
  );
  const [connectionId, setConnectionId] = useState<string | null>(connections[0]?.id ?? null);
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  // The upload's Idempotency-Key (DG-FE-05 rev 1.156): the same file sent again after a lost answer
  // carries the key it had. The attach command below keeps its own through `useCommand`.
  const uploadKeys = useCommandKeys();
  const command = useCommand({
    method: "POST",
    path: `${RECONCILIATIONS_PATH}/${id}/attach-trial-balance`,
    invalidates: COMMAND_KEYS,
  });

  const send = async (body: ReconciliationAttachIn) => {
    const outcome = await command.submit(body satisfies ReconciliationAttachIn);
    if (outcome.kind === "accepted" || outcome.kind === "succeeded") {
      // The record states the request from now on, for this reader as for every other.
      await queryClient.invalidateQueries({ queryKey: reconciliationKey(id) });
    } else if (outcome.kind === "failed" && outcome.problem.status === 409) {
      onRefused(outcome.problem);
    }
  };
  const upload = async () => {
    if (file === null) {
      setFileError(t("close.reconciliation.attach.fileMissing"));
      return;
    }
    setFileError(null);
    setUploading(true);
    try {
      const stored = await uploadFile(uploadKeys, TRIAL_BALANCE_PURPOSE, file);
      await send({ file_id: stored.id });
    } catch (error) {
      // ERR-37: the detail names the limit of the purpose.
      setFileError(
        error instanceof ApiProblem
          ? (error.detail ?? error.title)
          : t("close.reconciliation.problem.network"),
      );
    } finally {
      setUploading(false);
    }
  };

  const selected =
    mode === UPLOAD_MODE
      ? null
      : (connections.find((connection) => connection.id === (segmented ? mode : connectionId)) ??
        null);
  const segments: SegmentOption<string>[] = [
    ...(segmented
      ? connections.map((connection) => ({
          value: connection.id,
          label: t("close.reconciliation.attach.segment.pull", { connection: connection.name }),
        }))
      : [{ value: CONNECTION_MODE, label: t("close.reconciliation.attach.segment.connection") }]),
    ...(canUpload
      ? [{ value: UPLOAD_MODE, label: t("close.reconciliation.attach.segment.upload") }]
      : []),
  ];
  const busy = command.pending || uploading;
  // A 409 is the record's and shows on the page; every other refusal shows here. A file that cannot
  // be compared names its findings by row and column (04 §16.8 `attach-trial-balance`, 422).
  const problem =
    command.problem !== null && command.problem.status !== 409 ? command.problem : null;
  const findings = problem === null ? [] : problem.errors.filter((error) => error.field !== null);

  return (
    <section
      data-testid="SF-05-attach-trial-balance"
      className="flex flex-col gap-3 rounded-md border border-hairline bg-surface p-4"
    >
      {state === "attaching" && request !== null ? (
        <div data-testid="SF-05-job-trial-balance">
          <JobProgress
            label={t("close.reconciliations.generating", { kind: kindLabel(reconciliation.kind) })}
            job={{
              id: request.job.id,
              state: request.job.state,
              progress: { done: 0, total: null },
              started_at: request.job.created_at,
              problem: null,
            }}
            unit={t("close.reconciliation.attach.unit")}
          />
        </div>
      ) : null}
      {failed === null ? null : (
        <div data-testid="SF-05-banner-attach-failed">
          <Banner
            tone="negative"
            announce="static"
            title={
              failed.source === "ADAPTER"
                ? t("close.reconciliation.attach.pullFailed", {
                    connection:
                      failed.integration_connection?.name ??
                      t("close.reconciliation.attach.theConnection"),
                    problem:
                      failed.job.problem?.title ?? t("close.reconciliation.attach.problemUnnamed"),
                  })
                : t("close.reconciliation.attach.fileFailed", {
                    problem:
                      failed.job.problem?.title ?? t("close.reconciliation.attach.problemUnnamed"),
                  })
            }
          >
            {failed.source === "FILE" && (failed.job.problem?.detail ?? null) !== null ? (
              <p>{failed.job.problem?.detail}</p>
            ) : null}
          </Banner>
        </div>
      )}
      <div className="flex max-w-120 flex-col gap-1">
        <h2 className="text-title-sm text-fg-1">{t("close.reconciliation.attach.title")}</h2>
        <p className="text-body-sm text-fg-2">
          {mayAttach && connections.length === 0
            ? // The preparer is told what this entity offers, not what another might.
              `${t("close.reconciliation.attach.noConnection", { entity })}${
                canUpload ? ` ${t("close.reconciliation.attach.uploadInstead")}` : ""
              }`
            : t("close.reconciliation.attach.description", { entity, period: label })}
        </p>
      </div>
      {mayAttach ? (
        <div className="flex flex-col items-start gap-3">
          {segments.length < 2 ? null : (
            // DS-CMP-31 holds two to five options: one connection without the upload needs no choice.
            <SegmentedControl
              label={t("close.reconciliation.attach.source")}
              options={segments}
              value={mode}
              onChange={setMode}
            />
          )}
          {problem === null ? null : (
            <div className="flex w-full flex-col gap-2">
              {/* The findings below are every message that names a row or a column. */}
              <RefusalBanner problem={problem} placed={LISTED_BY_THE_SCREEN} />
              {findings.length === 0 ? null : (
                <ul className="flex flex-col gap-0.5 text-body-sm text-fg-1">
                  {findings.map((error) => (
                    <li key={`${String(error.row)}:${error.field ?? ""}:${error.message}`}>
                      {error.row === null || error.field === "file_id"
                        ? error.message
                        : t("close.reconciliation.attach.finding", {
                            row: formatNumber(error.row, { kind: "count" }),
                            column: error.field ?? "",
                            message: error.message,
                          })}
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {mode === UPLOAD_MODE ? (
            canUpload ? (
              <>
                <TrialBalanceDropzone
                  file={file}
                  error={fileError}
                  onFile={(chosen) => {
                    setFile(chosen);
                    setFileError(null);
                  }}
                />
                <Button variant="primary" loading={busy} onClick={() => void upload()}>
                  {t("close.reconciliation.attach.compare")}
                </Button>
              </>
            ) : null
          ) : (
            <>
              {segmented ? null : (
                <SelectField
                  name="trial-balance-connection"
                  label={t("close.reconciliation.attach.connection")}
                  options={connections.map((connection) => ({
                    value: connection.id,
                    label: connection.name,
                  }))}
                  value={connectionId}
                  onChange={setConnectionId}
                />
              )}
              {selected === null ? null : (
                <Button
                  variant="primary"
                  loading={busy}
                  onClick={() =>
                    void send({ source: "ADAPTER", integration_connection_id: selected.id })
                  }
                >
                  {t("close.reconciliation.attach.pull", { connection: selected.name })}
                </Button>
              )}
            </>
          )}
        </div>
      ) : null}
    </section>
  );
}

/** DS-CMP-18 dropzone anatomy: a button backed by a native file input; dropping a file is optional. */
function TrialBalanceDropzone({
  file,
  error,
  onFile,
}: {
  readonly file: File | null;
  readonly error: string | null;
  readonly onFile: (file: File) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [over, setOver] = useState(false);
  const labelId = useId();
  const limitId = useId();
  const errorId = useId();
  const drop = (event: DragEvent<HTMLButtonElement>) => {
    event.preventDefault();
    setOver(false);
    const dropped = event.dataTransfer.files[0];
    if (dropped !== undefined) {
      onFile(dropped);
    }
  };
  return (
    <div className="flex w-full max-w-xl flex-col gap-1.5">
      <span id={labelId} className="text-body-sm font-medium text-fg-1">
        {t("close.reconciliation.attach.file")}
      </span>
      <button
        type="button"
        data-testid="SF-05-trial-balance-dropzone"
        aria-describedby={error === null ? limitId : `${limitId} ${errorId}`}
        onClick={() => input.current?.click()}
        onDragOver={(event) => {
          event.preventDefault();
          setOver(true);
        }}
        onDragLeave={() => setOver(false)}
        onDrop={drop}
        className={cn(
          "flex h-32 w-full flex-col items-center justify-center gap-2 rounded-lg border border-dashed bg-surface px-4 text-body-sm text-fg-2 hover:bg-hover",
          error === null ? "border-control" : "border-negative-fg",
          over ? "bg-hover" : null,
        )}
      >
        <UploadSimple aria-hidden="true" size={24} className="text-fg-3" />
        <span>{t("data.imports.upload.dropzone")}</span>
        <span className="inline-flex h-8 items-center rounded-md border border-control bg-surface px-3 font-medium text-fg-1">
          {t("data.imports.upload.choose")}
        </span>
      </button>
      <input
        ref={input}
        type="file"
        hidden
        accept={TRIAL_BALANCE_FILES}
        data-testid="SF-05-trial-balance-file"
        aria-labelledby={labelId}
        onChange={(event) => {
          const chosen = event.target.files?.[0];
          if (chosen !== undefined) {
            onFile(chosen);
          }
          event.target.value = "";
        }}
      />
      {file === null ? null : (
        <p data-testid="SF-05-trial-balance-selected" className="text-body-sm text-fg-1">
          {t("data.imports.upload.selected", {
            name: file.name,
            size: formatNumber(file.size, { kind: "count" }),
          })}
        </p>
      )}
      <p id={limitId} className="text-body-sm text-fg-3">
        {t("data.imports.upload.limit")}
      </p>
      {error === null ? null : (
        <p id={errorId} role="alert" className="text-body-sm text-negative-fg">
          {error}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------
// Header: key figures.

interface Figure {
  readonly id: string;
  readonly label: string;
  /** One line per currency for money, one line for a count. */
  readonly lines: readonly { readonly key: string; readonly value: ReactNode }[];
}

/**
 * DS-CMP-06 KPI strip "Key figures (<currency>)" (SCREENS_B §2.2). Money is never added here
 * (DG-FE-08): the figures are the rows of API-S-Reconciliation `summary`, one per currency, summed by
 * the server. Several currencies read one line each with their code (DS-FMT-12).
 */
function KeyFigures({ reconciliation }: { readonly reconciliation: Reconciliation }) {
  const headingId = useId();
  const summary = reconciliation.summary;
  const [only] = summary;
  const single = summary.length === 1 && only !== undefined ? only.currency : null;
  const money = (pick: (row: ReconciliationSummary) => string): Figure["lines"] =>
    summary.length === 0
      ? [{ key: "none", value: <NoValue /> }]
      : summary.map((row) => ({
          key: row.currency,
          value: currencyRegistered(row.currency) ? (
            formatMoney(pick(row), row.currency, { variant: single === null ? "inline" : "cell" })
          ) : (
            <NoValue />
          ),
        }));
  const count = (value: number): Figure["lines"] => [
    { key: "count", value: formatNumber(value, { kind: "count" }) },
  ];
  // The accounts of each currency as the API counts them. A billing reconciliation's totals carry no
  // account, so the figure does not apply to it.
  let accounts: Figure["lines"] | null = null;
  if (summary.some((row) => row.account_count > 0)) {
    accounts =
      summary.length === 1 && only !== undefined
        ? count(only.account_count)
        : summary.map((row) => ({
            key: row.currency,
            value: `${row.currency}${NBSP}${formatNumber(row.account_count, { kind: "count" })}`,
          }));
  }
  const figures: readonly Figure[] = [
    ...(accounts === null
      ? []
      : [{ id: "accounts", label: t("close.reconciliation.kpi.accounts"), lines: accounts }]),
    {
      id: "subledger-total",
      label: t("close.reconciliation.kpi.subledgerTotal"),
      lines: money((row) => row.subledger_amount.amount),
    },
    {
      id: "source-total",
      label: t("close.reconciliation.kpi.sourceTotal", { source: sourceLabel(reconciliation) }),
      lines: money((row) => row.source_amount.amount),
    },
    {
      id: "difference",
      label: t("close.reconciliation.kpi.difference"),
      lines: money((row) => row.difference.amount),
    },
    {
      id: "variances",
      label: t("close.reconciliation.kpi.variances"),
      lines: count(reconciliation.variance_count),
    },
  ];
  return (
    <section
      aria-labelledby={headingId}
      data-testid="SF-05-kpi-strip"
      className="flex flex-col gap-2 border-t border-hairline pt-3"
    >
      <h2 id={headingId} className="text-caption text-fg-3">
        {single === null
          ? t("close.reconciliation.kpi.headingMixed")
          : t("close.reconciliation.kpi.heading", { currency: single })}
      </h2>
      <dl className="flex flex-wrap gap-y-3">
        {figures.map((figure) => (
          <div
            key={figure.id}
            data-testid={`SF-05-kpi-${figure.id}`}
            className="flex min-w-40 flex-col gap-1 border-s border-hairline px-4 first:border-s-0 first:ps-0"
          >
            <dt className="text-caption text-fg-3">{figure.label}</dt>
            {figure.lines.map((line) => (
              <dd key={line.key} className="num text-kpi text-fg-1">
                {line.value}
              </dd>
            ))}
          </div>
        ))}
      </dl>
    </section>
  );
}

// ---------------------------------------------------------------------------------------------------
// Totals by account.

function totalKey(total: ReconciliationTotal): string {
  return `${total.account_code ?? ""}|${total.currency}`;
}

function TotalsGrid({
  reconciliation,
  periodLabel: label,
}: {
  readonly reconciliation: Reconciliation;
  readonly periodLabel: string;
}) {
  const totals = reconciliation.totals;
  const currencies = currenciesOf(totals, []);
  const single = currencies.length === 1 ? (currencies[0] ?? null) : null;
  const sourceName = sourceLabel(reconciliation);
  // The record carries its totals: the grid reads them as one page, again whenever the record changes.
  const source: GridSource<ReconciliationTotal> = {
    queryKey: queryKey("reconciliations", "tenant", {
      id: reconciliation.id,
      view: "totals-grid",
      row_version: reconciliation.row_version,
    }),
    fetchPage: () =>
      Promise.resolve({
        items: totals,
        nextCursor: null,
        total: { count: totals.length, capped: false },
      }),
  };
  const columns = useMemo(
    (): readonly GridColumn<ReconciliationTotal>[] => [
      {
        id: "account",
        header: t("close.reconciliation.totals.column.account"),
        kind: "text",
        value: (total) => total.account_code,
        render: (total) =>
          total.account_code === null ? <NoValue /> : <Mono>{total.account_code}</Mono>,
        width: 136,
      },
      {
        id: "currency",
        header: t("close.reconciliation.totals.column.currency"),
        kind: "text",
        currencyColumn: true,
        value: (total) => total.currency,
        render: (total) => <Mono>{total.currency}</Mono>,
        width: 104,
      },
      {
        id: "subledger",
        header: amountHeader("subledger", single),
        kind: "money",
        value: (total) => total.subledger_amount?.amount ?? null,
        currency: (total) => total.currency,
        render: (total) => (
          <MoneyCell value={total.subledger_amount?.amount ?? null} currency={total.currency} />
        ),
        width: 192,
      },
      {
        // "<source label> (<currency>)": GL, Billing or Rollforward (SCREENS_B §2.2).
        id: "source",
        header: single === null ? sourceName : `${sourceName} (${single})`,
        kind: "money",
        value: (total) => total.source_amount?.amount ?? null,
        currency: (total) => total.currency,
        render: (total) => (
          <MoneyCell value={total.source_amount?.amount ?? null} currency={total.currency} />
        ),
        width: 192,
      },
      {
        id: "difference",
        header: amountHeader("difference", single),
        kind: "money",
        // 04 §16.8 rev 1.253: a role row the subledger does not state carries no difference.
        value: (total) => total.difference?.amount ?? null,
        currency: (total) => total.currency,
        // DS-FMT-30: a difference that is not zero carries the chip; the amount keeps its ink.
        render: (total) => (
          <span className="inline-flex items-center justify-end gap-2">
            {total.difference === null || isZeroAmount(total.difference.amount) ? null : (
              <StatusChip status="Difference" />
            )}
            <MoneyCell value={total.difference?.amount ?? null} currency={total.currency} />
          </span>
        ),
        width: 256,
      },
    ],
    [single, sourceName],
  );
  // A billing reconciliation's totals carry no account (04 API-S-Reconciliation), so the column starts
  // hidden there; it stays in the column chooser.
  const hasAccounts = totals.some((total) => total.account_code !== null);
  const defaultColumns = useMemo(
    (): GridColumnState => initialColumnState(columns, hasAccounts ? [] : ["account"]),
    [columns, hasAccounts],
  );
  return (
    <div className="flex min-h-40 flex-col">
      <DataGrid<ReconciliationTotal>
        name="recon-totals"
        title={t("close.reconciliation.totals.title")}
        errorTitle={t("close.reconciliation.totals.loadError")}
        countLabel={(count, formatted) =>
          t("close.reconciliation.totals.count", { count, formatted })
        }
        columns={columns}
        source={source}
        rowKey={totalKey}
        rowLabel={(total) =>
          total.account_code === null ? total.currency : `${total.account_code} ${total.currency}`
        }
        testIdPrefix="SF-05"
        defaultColumnState={defaultColumns}
        emptyState={
          <EmptyState
            title={t("close.reconciliation.totals.emptyTitle")}
            description={t("close.reconciliation.totals.emptyDescription", { period: label })}
            headingLevel={3}
          />
        }
      />
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------
// Differences.

/** SCR-TID-03: the reference of a difference, else its classification and account; never an id. */
function itemTestKey(item: ReconciliationItem): string {
  return (
    itemReference(item) ??
    [item.item_kind, item.account_code].filter((part) => part !== null).join("-")
  );
}

interface DifferencesGridProps {
  readonly reconciliation: Reconciliation;
  /** Explanations change: a current draft in a workable period, for a holder of `recon.prepare`. */
  readonly editable: boolean;
  readonly ctxSearch: string;
  readonly contractsBuilt: boolean;
  readonly onExplain: (item: ReconciliationItem) => void;
}

function DifferencesGrid({
  reconciliation,
  editable,
  ctxSearch,
  contractsBuilt,
  onExplain,
}: DifferencesGridProps) {
  const queryClient = useQueryClient();
  const id = reconciliation.id;
  const items = useQuery({
    queryKey: reconciliationItemsKey(id),
    queryFn: () => fetchReconciliationItems(id),
  });
  const currencies = currenciesOf(reconciliation.totals, items.data?.items ?? []);
  const single = currencies.length === 1 ? (currencies[0] ?? null) : null;
  const billing = reconciliation.kind === "BILLING_TO_SUBLEDGER";
  const source: GridSource<ReconciliationItem> = useMemo(
    () => ({
      queryKey: queryKey("reconciliations", "tenant", { id, view: "items-grid" }),
      // The differences are one read, in the order they were itemised; the grid shows it as one page.
      fetchPage: async () => {
        const data = await queryClient.fetchQuery({
          queryKey: reconciliationItemsKey(id),
          queryFn: () => fetchReconciliationItems(id),
        });
        return {
          items: data.items,
          nextCursor: null,
          total: { count: data.items.length, capped: data.truncated },
        };
      },
    }),
    [queryClient, id],
  );
  const columns = useMemo((): readonly GridColumn<ReconciliationItem>[] => {
    const amount = (
      columnId: "subledger" | "source" | "difference",
      pick: (item: ReconciliationItem) => string | null,
    ): GridColumn<ReconciliationItem> => ({
      id: columnId,
      header: amountHeader(columnId, single),
      kind: "money",
      value: pick,
      currency: (item) => item.currency,
      render: (item) => <MoneyCell value={pick(item)} currency={item.currency} />,
      // Wide enough for "Difference (<currency>)" beside the column menu.
      width: 160,
    });
    return [
      {
        // The row header names the classification (SCREENS_B §2.2 test hooks).
        id: "kind",
        header: t("close.reconciliation.items.column.kind"),
        kind: "identifier",
        value: itemKindLabel,
        render: (item) => (
          <span className="truncate" title={itemKindLabel(item)}>
            {itemKindLabel(item)}
          </span>
        ),
        // The long classification of a direct GL entry truncates with its title, so that the amounts
        // and "Explanation" stay in view at 1440 px (DS-CMP-10 rows are one line).
        width: 200,
      },
      {
        id: "account",
        header: t("close.reconciliation.items.column.account"),
        kind: "text",
        value: (item) => item.account_code,
        render: (item) =>
          item.account_code === null ? <NoValue /> : <Mono>{item.account_code}</Mono>,
        width: 104,
      },
      {
        id: "contract",
        header: t("close.reconciliation.items.column.contract"),
        kind: "text",
        value: (item) => item.contract?.external_id ?? null,
        render: (item) => {
          if (item.contract === null) {
            return <NoValue />;
          }
          return contractsBuilt ? (
            <Link
              to={`/contracts/${item.contract.id}${ctxSearch}`}
              tabIndex={-1}
              className="truncate font-mono text-mono-sm text-accent-fg hover:underline"
            >
              {item.contract.external_id}
            </Link>
          ) : (
            <Mono>{item.contract.external_id}</Mono>
          );
        },
        width: 152,
      },
      {
        id: "reference",
        header: t("close.reconciliation.items.column.reference"),
        kind: "text",
        value: itemReference,
        render: (item) => {
          const reference = itemReference(item);
          return reference === null ? <NoValue /> : <Mono>{reference}</Mono>;
        },
        width: 128,
      },
      ...(single === null
        ? [
            {
              id: "currency",
              header: t("close.reconciliation.totals.column.currency"),
              kind: "text",
              currencyColumn: true,
              value: (item) => item.currency,
              render: (item) => <Mono>{item.currency}</Mono>,
              width: 104,
            } satisfies GridColumn<ReconciliationItem>,
          ]
        : []),
      amount("subledger", (item) => item.subledger_amount?.amount ?? null),
      amount("source", (item) => item.source_amount?.amount ?? null),
      // [J] CLO-25: API-R-49 names no object type for a reconciliation difference (04 §16.11), so the
      // figure carries no Explain trigger yet.
      amount("difference", (item) => item.difference.amount),
      {
        id: "risk",
        header: t("close.reconciliation.items.column.risk"),
        kind: "text",
        value: (item) => (item.is_high_risk ? t("close.reconciliation.items.highRisk") : null),
        render: (item) =>
          item.is_high_risk ? (
            <OutlineChip label={t("close.reconciliation.items.highRisk")} />
          ) : null,
        width: 96,
      },
      {
        id: "explanation",
        header: t("close.reconciliation.items.column.explanation"),
        kind: "text",
        value: (item) => item.explanation,
        render: (item) => {
          const text = item.explanation?.trim() ?? "";
          if (text === "") {
            return editable ? (
              <Button variant="ghost" size="sm" tabIndex={-1} onClick={() => onExplain(item)}>
                {t("close.reconciliation.items.addExplanation")}
              </Button>
            ) : (
              <NoValue />
            );
          }
          return (
            <button
              type="button"
              tabIndex={-1}
              title={text}
              onClick={() => onExplain(item)}
              className="min-w-0 truncate rounded-sm text-start text-fg-1 decoration-control decoration-dotted underline-offset-4 hover:underline focus-visible:underline"
            >
              {text}
            </button>
          );
        },
        // Enter opens the drawer as a click does; an empty explanation opens it only while editable.
        activate: (item) => {
          if (editable || (item.explanation?.trim() ?? "") !== "") {
            onExplain(item);
          }
        },
        width: 320,
      },
      {
        id: "resolved",
        header: t("close.reconciliation.items.column.resolved"),
        kind: "text",
        value: (item) =>
          item.resolved_at === null
            ? null
            : `${formatTimestamp(item.resolved_at)} · ${item.resolved_by?.display_name ?? ""}`,
        render: (item) =>
          item.resolved_at === null ? (
            <NoValue />
          ) : (
            <span className="truncate">
              <span data-volatile="">{formatTimestamp(item.resolved_at)}</span>
              {item.resolved_by === null ? null : ` · ${item.resolved_by.display_name}`}
            </span>
          ),
        width: 288,
      },
    ];
  }, [single, editable, contractsBuilt, ctxSearch, onExplain]);
  // A billing difference names a contract and no account or risk; a ledger difference the reverse.
  // "Resolved" appears in neither wireframe. Every column stays in the column chooser.
  const defaultColumns = useMemo(
    (): GridColumnState =>
      initialColumnState(
        columns,
        billing ? ["account", "risk", "resolved"] : ["contract", "resolved"],
      ),
    [columns, billing],
  );
  return (
    <div className="flex min-h-64 flex-col">
      <DataGrid<ReconciliationItem>
        // The Currency column comes and goes with the currencies of the differences.
        key={single === null ? "mixed" : "single"}
        name="recon-items"
        title={t("close.reconciliation.items.title")}
        errorTitle={t("close.reconciliation.items.loadError")}
        countLabel={(count, formatted) =>
          items.data?.truncated === true
            ? t("close.reconciliation.items.truncated", { formatted })
            : t("close.reconciliation.items.count", { count, formatted })
        }
        columns={columns}
        source={source}
        rowKey={(item) => item.id}
        rowLabel={(item) => itemReference(item) ?? itemKindLabel(item)}
        testIdPrefix="SF-05"
        rowTestKey={itemTestKey}
        defaultColumnState={defaultColumns}
        emptyState={
          <EmptyState
            title={t("close.reconciliation.items.emptyTitle")}
            description={t("close.reconciliation.items.emptyDescription")}
            headingLevel={3}
          />
        }
      />
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------
// Sign-offs.

const SIGNING_ROLES = ["PREPARER", "REVIEWER"] as const;

/** SCREENS_B §2.2 "Sign-offs": the preparer's and the reviewer's statements with signer and UTC time. */
function Signoffs({ reconciliation }: { readonly reconciliation: Reconciliation }) {
  const headingId = useId();
  return (
    <section
      aria-labelledby={headingId}
      data-testid="SF-05-signoffs"
      className="flex flex-col gap-3 rounded-md border border-hairline bg-surface p-4"
    >
      <h2 id={headingId} className="text-title-sm text-fg-1">
        {t("close.reconciliation.signoffs.title")}
      </h2>
      <dl className="flex flex-wrap gap-x-10 gap-y-3">
        {SIGNING_ROLES.map((role) => {
          const signed = signoffsOf(reconciliation, role);
          const system = role === "PREPARER" && reconciliation.auto_certify_rule !== null;
          return (
            <div key={role} className="flex min-w-72 flex-1 flex-col gap-1">
              <dt className="text-caption text-fg-3">
                {t(`close.reconciliation.signoffs.role.${role}`)}
              </dt>
              {signed.length === 0 ? (
                <dd className="text-body-sm text-fg-1">
                  {system ? t("close.reconciliations.system") : <NoValue />}
                </dd>
              ) : (
                signed.map((signoff) => (
                  <dd key={signoff.id} className="flex flex-col gap-0.5">
                    <span className="text-body-sm text-fg-1">
                      {signoff.signer.display_name}
                      {" · "}
                      <span data-volatile="" className="num">
                        {formatTimestamp(signoff.signed_at)}
                      </span>
                    </span>
                    <q className="text-body-sm text-fg-2">{signoff.statement}</q>
                  </dd>
                ))
              )}
            </div>
          );
        })}
      </dl>
    </section>
  );
}

// ---------------------------------------------------------------------------------------------------
// Commands.

interface SignDialogProps {
  readonly title: string;
  /** The fixed statement of the sign-off (T-CLS-08). */
  readonly statement: string;
  readonly action: string;
  readonly command: CommandState<ReconciliationOut>;
  readonly onSign: () => void;
  readonly onClose: () => void;
}

/**
 * SCREENS_B §2.2 "Sign as preparer" and "Sign as reviewer" (DS-CMP-11 confirmation): the statement and
 * the checkbox "I confirm this statement", a client-side gate (OQ-B-05). The statement is part of the
 * checkbox's label (§2.2 accessibility).
 */
function SignDialog({ title, statement, action, command, onSign, onClose }: SignDialogProps) {
  const statementId = useId();
  const confirmId = useId();
  const checkboxId = useId();
  const errorId = useId();
  const [accepted, setAccepted] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const missing = attempted && !accepted;
  return (
    <Modal
      open
      variant="confirmation"
      title={title}
      primaryAction={{
        label: action,
        onAction: () => {
          setAttempted(true);
          if (accepted) {
            onSign();
          }
        },
      }}
      submitting={command.pending}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3">
        <RefusalBanner problem={command.problem} />
        <p id={statementId} className="text-body text-fg-1">
          {statement}
        </p>
        <div className="flex flex-col gap-1">
          <span className="flex items-center gap-2 text-body-sm text-fg-1">
            <input
              id={checkboxId}
              type="checkbox"
              checked={accepted}
              aria-labelledby={`${confirmId} ${statementId}`}
              aria-invalid={missing ? true : undefined}
              aria-describedby={missing ? errorId : undefined}
              onChange={(event) => {
                setAccepted(event.target.checked);
              }}
              className="size-4"
            />
            <label id={confirmId} htmlFor={checkboxId}>
              {t("close.reconciliation.sign.confirm")}
            </label>
          </span>
          {missing ? (
            <p id={errorId} className="text-body-sm text-negative-fg">
              {t("close.reconciliation.sign.unconfirmed")}
            </p>
          ) : null}
        </div>
      </div>
    </Modal>
  );
}

// docs/dev-guide.md DG-FE-06: the one field of each of the two forms and the member it sends.
const REOPEN_MEMBERS = { reason: ["reason"] } as const;
const EXPLAIN_MEMBERS = { explanation: ["explanation"] } as const;

/** SB-R-05 "Reopen reconciliation": the consequence, a reason of at least 10 characters, Danger. */
function ReopenDialog({
  number,
  command,
  onReopen,
  onClose,
}: {
  readonly number: string;
  readonly command: CommandState<ReconciliationOut>;
  readonly onReopen: (reason: string) => void;
  readonly onClose: () => void;
}) {
  const [reason, setReason] = useState("");
  const [attempted, setAttempted] = useState(false);
  const placed = useMemo(() => placeProblem(command.problem, REOPEN_MEMBERS), [command.problem]);
  return (
    <Modal
      open
      variant="confirmation"
      title={t("close.reconciliation.reopen.title", { number })}
      description={t("close.reconciliation.reopen.description")}
      primaryAction={{
        label: t("close.reconciliation.action.reopen"),
        destructive: true,
        onAction: () => {
          setAttempted(true);
          if (reasonError(reason) === null) {
            onReopen(reason.trim());
          }
        },
      }}
      submitting={command.pending}
      onClose={onClose}
    >
      <div className="flex flex-col gap-3">
        <RefusalBanner problem={command.problem} placed={placed} />
        <ReasonField
          name="reconciliation-reopen-reason"
          label={t("close.reconciliation.reopen.reason")}
          value={reason}
          onChange={setReason}
          showError={attempted}
          error={placed.fields.reason}
        />
      </div>
    </Modal>
  );
}

interface ExplainDrawerProps {
  readonly reconciliation: Reconciliation;
  readonly item: ReconciliationItem;
  readonly editable: boolean;
  /** A refusal about the reconciliation itself (409): the page shows it and reads the record again. */
  readonly onRefused: (problem: ApiProblem) => void;
  readonly onClose: () => void;
}

/**
 * SCREENS_B §2.2 "Explain difference" (DS-CMP-09 modal drawer): the difference as a static table and
 * "Explanation (required)", at least 10 characters, saved with the item's `If-Match`. Outside a draft the
 * drawer shows the explanation in full and no field ([J] CLO-25: a reviewer reads every explanation).
 */
function ExplainDrawer({ reconciliation, item, editable, onRefused, onClose }: ExplainDrawerProps) {
  const formId = useId();
  const toast = useToast();
  const stored = item.explanation ?? "";
  const [text, setText] = useState(stored);
  const [attempted, setAttempted] = useState(false);
  const [unsent, setUnsent] = useState(false);
  const command = useCommand<ReconciliationItem>({
    method: "PATCH",
    path: `${RECONCILIATIONS_PATH}/${reconciliation.id}/items/${item.id}`,
    ifMatch: rowIfMatch(item.row_version),
    invalidates: COMMAND_KEYS,
  });
  const placed = useMemo(() => placeProblem(command.problem, EXPLAIN_MEMBERS), [command.problem]);
  const submit = async () => {
    setAttempted(true);
    if (reasonError(text) !== null) {
      return;
    }
    setUnsent(false);
    const outcome = await command.submit({
      explanation: text.trim(),
    } satisfies ReconciliationItemUpdateIn);
    if (outcome.kind === "succeeded") {
      toast.show({ tone: "positive", message: t("close.reconciliation.explain.saved") });
      onClose();
    } else if (outcome.kind === "network-error") {
      setUnsent(true);
    } else if (outcome.kind === "failed" && outcome.problem.status === 409) {
      // The reconciliation is no longer a current draft: the page says why and reads it again.
      onRefused(outcome.problem);
    }
  };
  const reference = itemReference(item);
  const amount = (value: string | null) =>
    value === null || !currencyRegistered(item.currency)
      ? NO_VALUE
      : formatMoney(value, item.currency, { variant: "inline" });
  const rows: readonly {
    readonly id: string;
    readonly label: string;
    readonly value: ReactNode;
  }[] = [
    {
      id: "kind",
      label: t("close.reconciliation.items.column.kind"),
      value: itemKindLabel(item),
    },
    {
      id: "account",
      label: t("close.reconciliation.items.column.account"),
      value: item.account_code === null ? NO_VALUE : <Mono>{item.account_code}</Mono>,
    },
    {
      id: "contract",
      label: t("close.reconciliation.items.column.contract"),
      value: item.contract === null ? NO_VALUE : <Mono>{item.contract.external_id}</Mono>,
    },
    {
      id: "reference",
      label: t("close.reconciliation.items.column.reference"),
      value: reference === null ? NO_VALUE : <Mono>{reference}</Mono>,
    },
    {
      id: "subledger",
      label: t("close.reconciliation.amount.subledger"),
      value: amount(item.subledger_amount?.amount ?? null),
    },
    {
      id: "source",
      label: t("close.reconciliation.amount.source"),
      value: amount(item.source_amount?.amount ?? null),
    },
    {
      id: "difference",
      label: t("close.reconciliation.amount.difference"),
      value: amount(item.difference.amount),
    },
  ];
  const table = (
    <div className="overflow-x-auto rounded-md border border-hairline">
      <table className="w-full border-collapse">
        <caption className="px-3 py-2 text-start text-title-sm text-fg-1">
          {t("close.reconciliation.explain.item")}
        </caption>
        <tbody>
          {rows.map((row) => (
            <tr key={row.id} className="border-t border-hairline">
              <th scope="row" className={`${CELL} w-40 text-start font-normal text-fg-3`}>
                {row.label}
              </th>
              <td className={`${CELL} text-fg-1`}>{row.value}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
  if (!editable) {
    return (
      <Drawer
        open
        title={t("close.reconciliation.explain.readTitle")}
        subtitle={reconciliation.reconciliation_no}
        initialFocus="title"
        onClose={onClose}
      >
        <div data-testid="SF-05-drawer-explain-difference" className="flex flex-col gap-4">
          {table}
          <dl className="flex flex-col gap-3">
            <div className="flex flex-col gap-0.5">
              <dt className="text-caption text-fg-3">
                {t("close.reconciliation.explain.explanation")}
              </dt>
              <dd className="whitespace-pre-wrap text-body text-fg-1">
                {stored.trim() === "" ? NO_VALUE : stored}
              </dd>
            </div>
            {item.resolved_at === null ? null : (
              <div className="flex flex-col gap-0.5">
                <dt className="text-caption text-fg-3">
                  {t("close.reconciliation.explain.explainedBy")}
                </dt>
                <dd className="text-body-sm text-fg-1">
                  {item.resolved_by === null ? null : `${item.resolved_by.display_name} · `}
                  <span data-volatile="" className="num">
                    {formatTimestamp(item.resolved_at)}
                  </span>
                </dd>
              </div>
            )}
          </dl>
        </div>
      </Drawer>
    );
  }
  return (
    <Drawer
      open
      title={t("close.reconciliation.explain.title")}
      subtitle={reconciliation.reconciliation_no}
      dirty={text !== stored}
      submitting={command.pending}
      initialFocus="field"
      banner={
        command.banner === null && command.problem === null && !unsent ? undefined : (
          <div className="flex flex-col gap-2">
            <RefusalBanner problem={command.problem} placed={placed} conflict={command.banner} />
            {unsent ? (
              <Banner
                tone="negative"
                title={t("close.reconciliation.problem.network")}
                announce="live"
              />
            ) : null}
          </div>
        )
      }
      primaryAction={{ label: t("close.reconciliation.explain.save"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-05-drawer-explain-difference"
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        {table}
        <ReasonField
          name="reconciliation-explanation"
          label={t("close.reconciliation.explain.field")}
          value={text}
          onChange={setText}
          showError={attempted}
          error={placed.fields.explanation}
        />
      </form>
    </Drawer>
  );
}
