// SF-07 Modification wizard (SCREENS §7.1 to §7.8, §7.10, §7.11, §7.13; §0.4 RT-20, RT-21; §0.6
// SCR-PERM-01; §0.7 SCR-ST-07, SCR-ST-12; DESIGN_SYSTEM DS-CMP-06, DS-CMP-18, DS-CMP-21, DS-CMP-24; 04
// API-R-31, §16.14 API-S-Modification, T-CON-06; PRD SM-03, BR-MOD-01, BR-MOD-02; docs/dev-guide.md
// DG-FE-05, DG-FE-08; BUILD_SPEC CTR-27).
//
// `ModificationWizard` (RT-20) holds step "Change" of a modification that does not exist yet: "Next"
// creates the draft and replaces the URL with SF-07:detail. `DraftWizard` is the wizard of a DRAFT on
// SF-07:detail, its step in `?step=change|questionnaire|treatment|preview|submit`:
// - Questionnaire: `/classify` proposes the answers the system can compute and stores none. An answer
//   counts once it is stored, by confirming its group or by changing it (BR-MOD-01; ruling R-82 (h));
//   every such save runs `/classify` again, because a `PATCH` clears the proposal.
// - Treatment: the chosen treatment per obligation and the SSP basis. A treatment other than the
//   proposal shows the override banner and needs a judgement record of topic
//   MODIFICATION_TREATMENT_OVERRIDE before "Next"; the API takes the submission once it is reviewed.
// - Impact preview: `/preview` is a 202 job; the stored preview is read from the row. Any later save
//   clears it, and the wizard says that the preview is out of date.
// - Submit: `/submit` routes the approval request; its refusals (REQ-PLT-015, REQ-MOD-002) are shown.
// The engine's price test of an added line is a fact of the row (`price_tests`, 04 §16.14 rev 1.250,
// item MOD-PRICE-TEST-FACT-1), stated whatever the preparer answered: its sentence stands under the
// price question, beside a proposal and beside a stored answer, and its range or point beside the
// SSP version of step "Treatment". The screen compares nothing and concludes nothing from it.
// `/classify` keeps a stored chosen treatment and fills in the proposal only where none is stored, so
// a save of step 1 or 2 sends `chosen_treatments` reduced to the departures the preparer made
// (`authoredChoices`): the defaults then follow the new proposal instead of standing as departures.
// No modification command takes `If-Match` (D-98 140-A4): two preparers on one draft are
// last-write-wins. "Discard draft" in the header voids the draft after a confirmation (`/discard`,
// PRD SM-03; a 409 names the judgement record whose review is pending, PRD ERR-82, or the linked
// estimate version that waits for approval, PRD ERR-83). The estimate versions created inside the
// draft are listed on step 1 and in the summary (`modification-linked.tsx`); `/submit` names each
// that is not approved (PRD ERR-87). Not rendered (XR-14): Explain on the preview figures (a dry run
// keeps no trace).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { Link, useBlocker, useLocation, useNavigate, useParams } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { JobProgress } from "../../components/feedback/JobProgress";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { Field } from "../../components/form/Field";
import { Select } from "../../components/form/Select";
import { NoValue } from "../../components/money/Num";
import { type Step, Stepper } from "../../components/record/Stepper";
import { Button } from "../../components/ui/Button";
import { Drawer } from "../../components/ui/Drawer";
import { Modal } from "../../components/ui/Modal";
import { chipFor, OutlineChip, StatusChip, statusMessageKey } from "../../components/ui/StatusChip";
import { StickyFooter } from "../../components/ui/StickyFooter";
import { announce } from "../../lib/a11y/announce";
import { useAccess } from "../../lib/access";
import { type CommandState, useCommand, useCommandKeys } from "../../lib/api/commands";
import { ApiProblem } from "../../lib/api/problems";
import {
  type Approval,
  approvalKey,
  currencyRegistered,
  fetchApproval,
  requestRoute,
} from "../../lib/api/queries/approvals";
import {
  type Contract,
  contractKey,
  fetchContract,
  fetchProductChoices,
  type Judgement,
  JUDGEMENTS_PATH,
  productChoicesKey,
  type RecordContext,
  sendCommand,
} from "../../lib/api/queries/contracts";
import { ESTIMATE_CREATE_PERMISSION } from "../../lib/api/queries/estimates";
import { judgementStatusLabel, recordStands } from "../../lib/api/queries/judgements";
import { useMe } from "../../lib/api/queries/me";
import {
  approvedSspVersionsKey,
  contractModificationsPath,
  fetchApprovedSspVersions,
  fetchLatestEvent,
  fetchLegacyRoute,
  fetchModificationJudgements,
  holdsStoredPreview,
  type JudgementCreateBody,
  type JudgementTopic,
  latestEventKey,
  LINKED_TOPICS,
  type Modification,
  MODIFICATION_CREATE_PERMISSION,
  MODIFICATION_LIST_KEYS,
  MODIFICATION_RECORD_KEYS,
  MODIFICATION_SUBJECT,
  type ModificationCreateBody,
  modificationJudgementsKey,
  modificationKey,
  modificationPath,
  modificationRoute,
  type ModificationSubmitBody,
  type ModificationTreatment,
  type ModificationUpdateBody,
  OVERRIDE_TOPIC,
  type Question,
  routeSelectionKey,
  type SspBasisBody,
  type SspVersionChoice,
  storedCatchUp,
} from "../../lib/api/queries/modifications";
import {
  contractObligationsKey,
  fetchContractObligations,
  fetchSspVersionLabel,
  type Obligation,
  type SspVersionLabel,
  sspVersionLabelKey,
} from "../../lib/api/queries/obligations";
import {
  entitiesKey,
  fetchActiveEntities,
  fetchPeriods,
  periodLabel as calendarLabel,
  periodsKey,
  STRUCTURE_READ_PERMISSION,
} from "../../lib/api/queries/tenant";
import type { components } from "../../lib/api/schema";
import {
  addedKeys,
  authoredChoices,
  changeFromModification,
  type ChangeContext,
  confirmedAnswers,
  departures,
  type DraftProgress,
  emptyChange,
  emptySubscription,
  firstOpenStep,
  isTreatment,
  LEGACY_TREATMENTS,
  type ObligationFacts,
  type Prefill,
  type PriceTest,
  priceTestOf,
  type QuestionGroup,
  questionGroups,
  questionnaireConfirmed,
  stepReachable,
  subscriptionActionOf,
  TREATMENTS,
  WIZARD_STEPS,
  type WizardStep,
  wizardStepOf,
  withAnswer,
  withGroupConfirmed,
  withoutGroup,
} from "../../lib/forms/modification";
import {
  formatDate,
  formatMoney,
  formatNumber,
  formatPercent,
  parseDateInput,
} from "../../lib/format";
import { hasMessage, t } from "../../lib/i18n/t";
import { withParams } from "../../lib/url/params";
import { useBuiltPaths } from "../settings/index";
import { TextField } from "./drawers/common";
import { DiscardRecord, type RecordContract, useRecordDiscard } from "./judgement-discard";
import { type ChangeVariant, ChangeStep, type Choice } from "./modification-change";
import { ModificationImpact, type PeriodLabel } from "./modification-impact";
import {
  LinkedEstimateVersions,
  LinkedVersionsSummary,
  linkedVersionsOf,
  unapprovedVersionLine,
} from "./modification-linked";
import { REQUEST_ROUTE } from "./obligation-pane";
import { contextSearch } from "./workbench";

type ModificationKind = components["schemas"]["ModificationKind"];

/** The reads of a modification screen take no period context: they show the row, not computed figures. */
const NO_CONTEXT: RecordContext = { book: null, asOf: null, knownAt: null };
const STEP_PARAM = "step";

// ---------------------------------------------------------------------------------------------------
// What every modification screen reads beside the modification itself.

export interface WizardBase {
  readonly contract: Contract;
  readonly obligations: readonly Obligation[];
  readonly context: ChangeContext;
  /** Obligation key → "<key> · <product code> · <date range>". */
  readonly obligationChoices: readonly Choice[];
  readonly periodLabel: PeriodLabel;
  /**
   * The key of the latest postable period (`open`, `closing`, `reopened`) of the contract's entity in
   * the primary book, as `GET /periods` answers it now; null where the entity has none, undefined
   * until the periods are read. A stored preview names the one its journal lines were computed for
   * (04 API-S-ImpactSummary `computed_period_key`, rev 1.210).
   */
  readonly latestPostablePeriod: string | null | undefined;
}

/** 04 E-04 states of a postable period, as API-S-ImpactSummary `computed_period_key` names them. */
const POSTABLE_STATES: ReadonlySet<string> = new Set(["open", "closing", "reopened"]);

function dateRange(start: string | null, end: string | null): string | null {
  if (start === null) {
    return end === null ? null : t("modifications.wizard.until", { end: formatDate(end) });
  }
  return end === null
    ? t("modifications.wizard.from", { start: formatDate(start) })
    : t("modifications.wizard.range", { start: formatDate(start), end: formatDate(end) });
}

function obligationText(item: Obligation): string {
  return [item.obligation_key, item.product.code, dateRange(item.start_date, item.end_date)]
    .filter((part): part is string => part !== null)
    .join(" · ");
}

type BaseState =
  | { readonly kind: "loading" }
  | { readonly kind: "not-found" }
  | { readonly kind: "error"; readonly error: unknown; readonly retry: () => void }
  | { readonly kind: "ready"; readonly base: WizardBase };

/** The contract, its obligations and the calendar labels of its entity. */
export function useWizardBase(contractId: string, enabled: boolean): BaseState {
  const contract = useQuery({
    queryKey: contractKey(contractId, NO_CONTEXT),
    queryFn: () => fetchContract(contractId, NO_CONTEXT),
    enabled,
    retry: (count, error) => !(error instanceof ApiProblem && error.status === 404) && count < 2,
  });
  const obligations = useQuery({
    queryKey: contractObligationsKey(contractId, NO_CONTEXT),
    queryFn: () => fetchContractObligations(contractId, NO_CONTEXT),
    enabled,
  });
  const entity = contract.data?.contracting_entity.code ?? null;
  const periods = useQuery({
    queryKey: periodsKey({ entity: entity ?? "" }),
    queryFn: () => fetchPeriods({ entity: entity ?? "" }),
    enabled: enabled && entity !== null,
    retry: false,
  });
  const periodLabel = useMemo((): PeriodLabel => {
    const labels = new Map<string, string>();
    for (const row of periods.data ?? []) {
      try {
        labels.set(row.period.period_key, calendarLabel(row.period));
      } catch {
        // A period the format module cannot label reads as its key.
      }
    }
    return (key) => labels.get(key) ?? key;
  }, [periods.data]);
  // The read asks no book, so it answers the periods of the primary book (04 API-R-18), the book of
  // a preview's dry run.
  const latestPostablePeriod = useMemo((): string | null | undefined => {
    if (periods.data === undefined) {
      return undefined;
    }
    const postable = periods.data
      .filter((row) => POSTABLE_STATES.has(row.state))
      .sort((left, right) => left.period.end_date.localeCompare(right.period.end_date));
    return postable[postable.length - 1]?.period.period_key ?? null;
  }, [periods.data]);
  const base = useMemo((): WizardBase | null => {
    if (contract.data === undefined || obligations.data === undefined) {
      return null;
    }
    const facts: ObligationFacts[] = obligations.data.map((item) => ({
      key: item.obligation_key,
      productCode: item.product.code,
      endDate: item.end_date,
    }));
    return {
      contract: contract.data,
      obligations: obligations.data,
      context: {
        externalId: contract.data.external_id,
        currency: contract.data.transaction_currency,
        obligations: facts,
      },
      obligationChoices: obligations.data.map((item) => ({
        value: item.obligation_key,
        label: obligationText(item),
      })),
      periodLabel,
      latestPostablePeriod,
    };
  }, [contract.data, obligations.data, periodLabel, latestPostablePeriod]);

  if (contract.isError && contract.error instanceof ApiProblem && contract.error.status === 404) {
    return { kind: "not-found" };
  }
  const failed = contract.isError ? contract : obligations.isError ? obligations : null;
  if (failed !== null) {
    return { kind: "error", error: failed.error, retry: () => void failed.refetch() };
  }
  if (base === null) {
    return { kind: "loading" };
  }
  // Amounts are parsed and shown in the contract currency; without its minor unit (the currency
  // reference was not readable) the screen does not open (DS-FMT-03, fail closed).
  return currencyRegistered(base.context.currency)
    ? { kind: "ready", base }
    : { kind: "error", error: null, retry: () => void contract.refetch() };
}

// ---------------------------------------------------------------------------------------------------
// The frame: breadcrumb, title with the status and the override chip, stepper, step content, footer.

export interface FrameProps {
  readonly testId: string;
  readonly contract: Contract | null;
  readonly ctxSearch: string;
  /** The `h1`: "New modification" or "Modification <reference>" (SCREENS §7.3). */
  readonly title: string;
  /** The last breadcrumb item; the title when not given. */
  readonly crumb?: string | undefined;
  /** The reference of a draft, beside the title. */
  readonly reference?: string | null | undefined;
  readonly status?: string | null | undefined;
  /** REQ-MOD-002: a chosen treatment differs from the proposal. */
  readonly override?: boolean;
  /** The line under the title: kind and effective date of a modification that is not a draft. */
  readonly meta?: ReactNode;
  readonly actions?: ReactNode;
  readonly children: ReactNode;
}

export function ModificationFrame({
  testId,
  contract,
  ctxSearch,
  title,
  crumb,
  reference,
  status,
  override = false,
  meta,
  actions,
  children,
}: FrameProps) {
  const chip = status === null || status === undefined ? null : chipFor("E-26", status);
  return (
    <div data-testid={testId} className="flex min-h-full flex-col gap-4">
      <header className="flex flex-col gap-3">
        <nav aria-label={t("common.record.breadcrumb")}>
          <ol className="flex flex-wrap items-center gap-1.5 text-body-sm text-fg-3">
            <li className="flex items-center gap-1.5">
              <Link to={`/contracts${ctxSearch}`} className="hover:text-fg-1 hover:underline">
                {t("contracts.workbench.breadcrumb")}
              </Link>
              <span aria-hidden="true">/</span>
            </li>
            {contract === null ? null : (
              <li className="flex items-center gap-1.5">
                <Link
                  to={`/contracts/${contract.id}/modifications${ctxSearch}`}
                  className="hover:text-fg-1 hover:underline"
                >
                  {contract.external_id}
                </Link>
                <span aria-hidden="true">/</span>
              </li>
            )}
            <li aria-current="page" className="min-w-0 truncate">
              {crumb ?? title}
            </li>
          </ol>
        </nav>
        <div className="flex flex-wrap items-center gap-3">
          <h1 id="modification-title" tabIndex={-1} className="text-title-lg text-fg-1">
            {title}
          </h1>
          {reference === null || reference === undefined ? null : (
            <span data-testid="SF-07-identifier" className="font-mono text-mono text-fg-2">
              {reference}
            </span>
          )}
          {chip === null ? null : <StatusChip status={chip.status} />}
          {override ? <OutlineChip label={t("modifications.wizard.override.chip")} /> : null}
          <span className="flex-1" />
          {actions}
        </div>
        {meta === undefined ? null : <p className="text-body-sm text-fg-2">{meta}</p>}
      </header>
      {children}
    </div>
  );
}

function AccessLimited() {
  return (
    <EmptyState
      title={t("settings.access.title", { area: t("modifications.access.area") })}
      description={t("settings.access.description", {
        permission: t("modifications.access.permission"),
      })}
      headingLevel={2}
    />
  );
}

export function LoadError({
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

/**
 * What a draft says of the request it was submitted with before (SCREENS §7.10), on the wizard and on
 * the read-only detail of a draft alike. A request the API voided because the modification changed
 * is a warning (NTF-04), as on an estimate version whose request the API voided. A rejected request
 * is the one the draft revises (PRD SM-03 "Revise"; 04 §16.14 rev 1.236, item
 * MOD-REJECTED-REVISE-1): it was decided and stays closed, the row names it until the next
 * submission makes a new one, and the notice names it by its number. A request its preparer
 * withdrew reads WITHDRAWN and shows nothing.
 */
export function DraftRequestNotice({
  request,
  ctxSearch,
}: {
  readonly request: Approval | undefined;
  readonly ctxSearch: string;
}) {
  const built = useBuiltPaths();
  if (request?.status === "VOIDED") {
    return (
      <Banner
        tone="warning"
        title={t("modifications.wizard.voided")}
        announce="static"
        headingLevel={2}
      />
    );
  }
  if (request?.status === "REJECTED") {
    return (
      <Banner
        tone="info"
        title={t("modifications.wizard.revised", { number: request.request_no })}
        announce="static"
        headingLevel={2}
        actions={
          built.has(REQUEST_ROUTE) ? (
            <Link
              to={`${requestRoute(request.id)}${ctxSearch}`}
              className="text-body-sm text-accent-fg hover:underline"
            >
              {t("contracts.workbench.banner.viewRequest")}
            </Link>
          ) : undefined
        }
      />
    );
  }
  return null;
}

/** What a command of the wizard ended with, when it did not succeed: the API's answer, or none. */
export type Failure = ApiProblem | "unreached";

/**
 * A stored preview this reader is not shown (SCREENS §7.7 and §7.9 rev 1.77; 04 §16.10 rev 1.300 "Who
 * reads a stored preview"): the API answers the preview to a member who holds `contract.read` for
 * every entity of the contract's combination group, and tells every other reader of the row that
 * one is stored. The notice stands in the place of the preview's tables, on step 4 and on
 * SF-07:detail, with the one figure the API answers to every reader of the row: the catch-up of the
 * contract's own obligations. A notice that follows a run of the step is inserted after load, and
 * announced.
 */
export function PreviewWithheld({
  row,
  announce = "static",
}: {
  readonly row: Modification;
  readonly announce?: "live" | "static";
}) {
  const catchUp = storedCatchUp(row);
  return (
    <div data-testid="SF-07-banner-preview-withheld">
      <Banner
        tone="info"
        title={t("modifications.impact.withheld.title")}
        announce={announce}
        headingLevel={3}
      >
        <p>{t("modifications.impact.withheld.text")}</p>
        {catchUp === null ? null : (
          <p>
            {t("modifications.impact.withheld.catchUp", {
              amount: formatMoney(catchUp.amount, catchUp.currency, {
                variant: "inline",
                delta: true,
              }),
            })}
          </p>
        )}
      </Banner>
    </div>
  );
}

/**
 * A command inside a step that did not succeed: the title, the detail and every message of `errors[]`
 * of a refusal, or the line of a server that did not answer. `onRetry` offers the command again.
 */
export function ProblemNotice({
  problem,
  onRetry,
}: {
  readonly problem: Failure | null;
  readonly onRetry?: (() => void) | undefined;
}) {
  if (problem === null) {
    return null;
  }
  const actions =
    onRetry === undefined ? undefined : (
      <Button variant="link" onClick={onRetry}>
        {t("common.grid.retry")}
      </Button>
    );
  if (problem === "unreached") {
    return (
      <Banner
        tone="negative"
        title={t("modifications.wizard.notReached")}
        announce="live"
        headingLevel={3}
        actions={actions}
      />
    );
  }
  const messages = [...new Set(problem.errors.map((error) => error.message))];
  return (
    <Banner
      tone="negative"
      title={problem.title}
      announce="live"
      headingLevel={3}
      actions={actions}
    >
      {problem.detail === null || messages.includes(problem.detail) ? null : (
        <p>{problem.detail}</p>
      )}
      {messages.map((message) => (
        <p key={message}>{message}</p>
      ))}
      {problem.requestId === null ? null : (
        <p>{t("contracts.drawer.reference", { reference: problem.requestId })}</p>
      )}
    </Banner>
  );
}

/** The failure of a command that did not answer 2xx: its problem, or "unreached". */
function failureOf(outcome: { readonly kind: string; readonly problem?: ApiProblem }): Failure {
  return outcome.kind === "failed" && outcome.problem !== undefined ? outcome.problem : "unreached";
}

interface FooterProps {
  /** What keeps "Next" from going on, as a line above the footer (SCREENS §7.3). */
  readonly blocked: string | null;
  readonly back: { readonly label: string; readonly onBack: () => void } | null;
  readonly next: ReactNode;
}

function WizardFooter({ blocked, back, next }: FooterProps) {
  return (
    <StickyFooter cueTestId="SF-07-more-below">
      {blocked === null ? null : (
        <p role="status" data-testid="SF-07-blocked" className="text-end text-body-sm text-fg-2">
          {blocked}
        </p>
      )}
      <div className="flex justify-end gap-2">
        {back === null ? null : (
          <Button variant="secondary" onClick={back.onBack}>
            {back.label}
          </Button>
        )}
        {next}
      </div>
    </StickyFooter>
  );
}

function kindLabel(kind: ModificationKind): string {
  return t(`modification.kind.${kind}`);
}

export function treatmentLabel(treatment: string): string {
  const key = `modifications.treatment.${treatment}`;
  return hasMessage(key) ? t(key) : treatment;
}

function stepLabel(step: WizardStep): string {
  return t(`modifications.wizard.steps.${step}`);
}

/** The steps of a modification that does not exist yet: "Change" is current, nothing is done. */
function newSteps(): readonly Step[] {
  return WIZARD_STEPS.map((step) => ({
    id: step,
    label: stepLabel(step),
    state: step === "change" ? "current" : "pending",
  }));
}

// ---------------------------------------------------------------------------------------------------
// RT-20: a new modification.

function useChangeChoices(base: WizardBase | null, general: boolean, structure: boolean) {
  const products = useQuery({
    queryKey: productChoicesKey(),
    queryFn: fetchProductChoices,
    enabled: base !== null && general,
  });
  const entities = useQuery({
    queryKey: entitiesKey(),
    queryFn: fetchActiveEntities,
    enabled: base !== null && general && structure,
  });
  const latest = useQuery({
    queryKey: latestEventKey(base?.contract.id ?? ""),
    queryFn: () => fetchLatestEvent(base?.contract.id ?? ""),
    enabled: base !== null,
    retry: false,
  });
  return {
    products: useMemo(
      (): readonly Choice[] =>
        (products.data ?? []).map((item) => ({
          value: item.code,
          label: `${item.code} · ${item.name}`,
        })),
      [products.data],
    ),
    entities: useMemo(
      (): readonly Choice[] =>
        (entities.data ?? []).map((item) => ({
          value: item.code,
          label: `${item.code} · ${item.name}`,
        })),
      [entities.data],
    ),
    latestEvent: latest.data ?? null,
    loading: general && products.isPending,
    error: general && products.isError ? products.error : null,
    retry: () => void products.refetch(),
  };
}

export function ModificationWizard() {
  const me = useMe();
  const params = useParams();
  const contractId = params.contractId ?? "";
  const location = useLocation();
  const navigate = useNavigate();
  const formId = useId();
  const ctxSearch = contextSearch(location.search);
  const search = new URLSearchParams(location.search);
  const permissions = me.data?.permissions ?? [];
  const allowed = permissions.includes(MODIFICATION_CREATE_PERMISSION);
  const state = useWizardBase(contractId, allowed);
  const base = state.kind === "ready" ? state.base : null;
  const action = subscriptionActionOf(search.get("action"));
  const choices = useChangeChoices(
    base,
    action === null,
    permissions.includes(STRUCTURE_READ_PERMISSION),
  );
  // One intent per body (DG-FE-05): a retry after a lost answer cannot create a second draft.
  const command = useCommand<Modification>({
    method: "POST",
    path: contractModificationsPath(contractId),
    invalidates: MODIFICATION_RECORD_KEYS,
  });
  const [unreached, setUnreached] = useState(false);
  const saving = command.pending;
  const [dirty, setDirty] = useState(false);
  const leaving = useRef(false);
  const blocker = useBlocker(
    ({ currentLocation, nextLocation }) =>
      dirty && !leaving.current && currentLocation.pathname !== nextLocation.pathname,
  );

  // SCR-URL-31: `kind` and `obligation` preselect the general form ("Change price" of an obligation).
  const kindParam = search.get("kind");
  const obligationParam = search.get("obligation");
  const variant = useMemo((): ChangeVariant | null => {
    if (base === null) {
      return null;
    }
    if (action !== null) {
      return { kind: "subscription", initial: emptySubscription(action, base.context.obligations) };
    }
    const preselected =
      base.obligations.find((item) => item.id === obligationParam)?.obligation_key ?? null;
    const kind =
      (Object.keys(KIND_OF) as ModificationKind[]).find((item) => item === kindParam) ?? null;
    return { kind: "general", initial: emptyChange("l1", kind, preselected) };
  }, [base, action, kindParam, obligationParam]);

  const cancel = () => void navigate(`/contracts/${contractId}/modifications${ctxSearch}`);
  const create = async (body: ModificationCreateBody) => {
    setUnreached(false);
    const outcome = await command.submit(body);
    if (outcome.kind !== "succeeded" || outcome.data === null) {
      setUnreached(outcome.kind !== "failed");
      return;
    }
    leaving.current = true;
    // SCREENS §7.3: the draft exists; the URL is replaced with SF-07:detail at the next step.
    void navigate(
      `${modificationRoute(contractId, outcome.data.id)}${withParams(ctxSearch, {
        [STEP_PARAM]: "questionnaire",
      })}`,
      { replace: true },
    );
  };

  const title = t("modifications.wizard.title.new");
  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={8} />;
  } else if (!allowed) {
    body = <AccessLimited />;
  } else if (state.kind === "not-found") {
    body = (
      <EmptyState
        title={t("contracts.workbench.notFound")}
        description={t("errors.notFound.description")}
        headingLevel={2}
        action={{
          label: t("contracts.workbench.goToContracts"),
          onAction: () => void navigate(`/contracts${ctxSearch}`),
        }}
      />
    );
  } else if (state.kind === "error") {
    body = (
      <LoadError
        title={t("contracts.workbench.loadError")}
        problem={state.error}
        onRetry={state.retry}
      />
    );
  } else if (base === null || variant === null) {
    body = <Skeleton region={title} shape="rows" count={8} />;
  } else if (base.contract.status !== "ACTIVE") {
    body = <NotActive contract={base.contract} onBack={cancel} />;
  } else if (choices.error !== null) {
    body = (
      <LoadError
        title={t("contracts.draft.loadError")}
        problem={choices.error}
        onRetry={choices.retry}
      />
    );
  } else if (choices.loading) {
    body = <Skeleton region={title} shape="rows" count={8} />;
  } else {
    body = (
      <>
        <div data-testid="SF-07-stepper">
          <Stepper
            label={t("modifications.wizard.stepper")}
            steps={newSteps()}
            currentId="change"
          />
        </div>
        <ProblemNotice problem={unreached ? "unreached" : null} />
        <ChangeStep
          formId={formId}
          variant={variant}
          context={base.context}
          obligationChoices={base.obligationChoices}
          products={choices.products}
          entities={choices.entities}
          latestEvent={choices.latestEvent}
          problem={command.problem}
          busy={saving}
          onDirty={setDirty}
          onBuilt={(built) => void create(built)}
        />
        <WizardFooter
          blocked={null}
          back={{ label: t("contracts.draft.cancel"), onBack: cancel }}
          next={
            <Button type="submit" form={formId} variant="primary" loading={saving}>
              {t("modifications.wizard.next")}
            </Button>
          }
        />
      </>
    );
  }
  return (
    <ModificationFrame
      testId="SF-07-page"
      contract={base?.contract ?? null}
      ctxSearch={ctxSearch}
      title={title}
      status={base === null ? null : "DRAFT"}
    >
      {body}
      <Modal
        open={blocker.state === "blocked"}
        variant="confirmation"
        title={t("common.dialog.discard.title")}
        description={t("common.dialog.discard.description")}
        primaryAction={{
          label: t("common.dialog.discard.confirm"),
          destructive: true,
          onAction: () => blocker.proceed?.(),
        }}
        onClose={() => blocker.reset?.()}
      />
    </ModificationFrame>
  );
}

/** E-25 literals, for reading the `kind` parameter of SCR-URL-31. */
const KIND_OF: Readonly<Record<ModificationKind, true>> = {
  ADD_OBLIGATION: true,
  REMOVE_OBLIGATION: true,
  QUANTITY_CHANGE: true,
  PRICE_CHANGE: true,
  TERM_CHANGE: true,
  UPGRADE: true,
  DOWNGRADE: true,
  CO_TERM: true,
  RENEWAL: true,
  CANCELLATION: true,
  TERMINATION: true,
  VC_CHANGE: true,
  OTHER: true,
  EARLY_RENEWAL: true,
};

/** SCREENS §7.10 "Contract not active". */
export function NotActive({
  contract,
  onBack,
}: {
  readonly contract: Contract;
  readonly onBack: () => void;
}) {
  const chip = chipFor("E-17", contract.status);
  return (
    <EmptyState
      title={t("modifications.wizard.notActive.title")}
      description={t("modifications.wizard.notActive.description", {
        id: contract.external_id,
        status: chip === null ? contract.status : t(statusMessageKey(chip.status)),
      })}
      headingLevel={2}
      action={{ label: t("contracts.draft.edit.backToContract"), onAction: onBack }}
    />
  );
}

// ---------------------------------------------------------------------------------------------------
// The wizard of a DRAFT.

type PreviewJob = components["schemas"]["JobOut"];

/** The member of a save for the choices it keeps; no member for a row without a proposal. */
function choicesOf(
  authored: Record<string, ModificationTreatment> | undefined,
): Pick<ModificationUpdateBody, "chosen_treatments"> {
  return authored === undefined ? {} : { chosen_treatments: authored };
}

function record(value: unknown): Readonly<Record<string, unknown>> {
  return typeof value === "object" && value !== null
    ? (value as Readonly<Record<string, unknown>>)
    : {};
}

/**
 * The row states the engine's proposal detail of its latest classification (CV-16; 04 §16.14 rev
 * 1.286 `proposal_detail`): never empty for a classified row, and `{}` for a row that is not
 * classified, was edited since or was classified before that revision. Before, the detail was the
 * member `proposal` of `prefill_reasons`, where an obligation of that name met it.
 */
function statesProposal(row: Modification): boolean {
  return Object.keys(record(row.proposal_detail)).length > 0;
}

/**
 * The row a classification answered, as the screen keeps it. `/classify` stores no answer
 * (BR-MOD-01), so the stored answers are those of the row it was asked for, `asked`: the kept row
 * holds them, as `GET` answers them, whatever the answer names as a proposal. The answer's own
 * `questionnaire` shows the proposed answers beside the stored ones (04 §16.14) and is not kept: a
 * proposal is read from `prefill_reasons`, and only for a question the row holds no answer to.
 */
function rowOfClassification(answer: Modification, asked: Modification): Modification {
  return { ...answer, questionnaire: asked.questionnaire };
}

/** The obligations of the row whose answers are not all stored: the classification may propose them. */
function openKeys(row: Modification): readonly string[] {
  const added = addedKeys(row);
  const stored = record(row.questionnaire);
  return [...new Set([...added, ...Object.keys(row.proposed_treatments)])].filter((key) => {
    const section = record(stored[key]);
    return added.includes(key)
      ? typeof section.added_goods_distinct !== "boolean" ||
          typeof section.priced_at_ssp !== "boolean"
      : typeof section.remaining_goods_distinct_from_transferred !== "boolean";
  });
}

/** T-PLT-11: preparing a judgement record (SCREENS §7.1 "linked judgements"). */
const JUDGEMENT_CREATE_PERMISSION = "judgement.create";

export interface DraftWizardProps {
  readonly base: WizardBase;
  /** The DRAFT as it was read. */
  readonly modification: Modification;
  /** The permissions of the session, for the reads that need `config.read`. */
  readonly permissions: readonly string[];
}

export function DraftWizard({ base, modification, permissions }: DraftWizardProps) {
  const { contract } = base;
  const location = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  const formId = useId();
  const ctxSearch = contextSearch(location.search);
  const requested = wizardStepOf(new URLSearchParams(location.search).get(STEP_PARAM)) ?? "change";
  const canJudge = permissions.includes(JUDGEMENT_CREATE_PERMISSION);

  // The row a command of this screen answered, kept beside the row that was read: the step, its
  // blocking line and the state of the command change in one render. The read stands once it is
  // newer (the preview job stores the preview and moves the version).
  const [answered, setAnswered] = useState<Modification | null>(null);
  const row =
    answered !== null &&
    answered.id === modification.id &&
    answered.row_version >= modification.row_version
      ? answered
      : modification;
  const apply = (next: Modification) => {
    setAnswered(next);
    queryClient.setQueryData(modificationKey(next.id), next);
  };

  // DG-FE-05: one hook per command, one Idempotency-Key per intent.
  const patch = useCommand<Modification>({ method: "PATCH", path: modificationPath(row.id) });
  const classifyCommand = useCommand<Modification>({
    method: "POST",
    path: `${modificationPath(row.id)}/classify`,
  });
  // The 202 job of `/preview` is adopted by the hook; the row is read again when it ends.
  const preview = useCommand<PreviewJob>({
    method: "POST",
    path: `${modificationPath(row.id)}/preview`,
    invalidates: [modificationKey(row.id)],
  });
  // `/submit` and `/discard` answer the row as `GET` does, with its stored preview (04 §16.14 rev
  // 1.188, item MOD-ANSWER-PREVIEW-1): the row is taken from the answer and only the lists are read
  // again.
  const submitCommand = useCommand<Modification>({
    method: "POST",
    path: `${modificationPath(row.id)}/submit`,
    invalidates: MODIFICATION_LIST_KEYS,
  });
  // SCREENS §7.3 (rev 1.26; PRD SM-03 "Discard draft", item MOD-DISCARD-1).
  const discardCommand = useCommand<Modification>({
    method: "POST",
    path: `${modificationPath(row.id)}/discard`,
    invalidates: MODIFICATION_LIST_KEYS,
  });

  // Step "Treatment" holds a choice that departs before it is saved: the header chip follows it.
  const [choosing, setChoosing] = useState(false);
  const [working, setWorking] = useState<"save" | "classify" | "submit" | null>(null);
  const [problem, setProblem] = useState<Failure | null>(null);
  const [dirty, setDirty] = useState(false);
  // A preview held in this session and cleared by a later save is "out of date" (SCREENS §7.7) —
  // one this reader is not shown as well (rev 1.77).
  const [hadPreview, setHadPreview] = useState(holdsStoredPreview(row));
  const [comment, setComment] = useState("");
  const [discarding, setDiscarding] = useState(false);
  const [discardProblem, setDiscardProblem] = useState<Failure | null>(null);
  const access = useAccess();
  const canDiscard = access.holds(MODIFICATION_CREATE_PERMISSION, contract.contracting_entity);
  // SCREENS §7.1: the linked estimate versions are prepared with `estimate.create`.
  const canEstimate = access.holds(ESTIMATE_CREATE_PERMISSION, contract.contracting_entity);
  // The row `/discard` answered. It replaces the draft in the cache once this screen is gone: set
  // while the screen stands, it would show the detail of the voided row for a moment before the
  // Modifications tab opens.
  const discarded = useRef<Modification | null>(null);
  useEffect(
    () => () => {
      if (discarded.current !== null) {
        queryClient.setQueryData(modificationKey(discarded.current.id), discarded.current);
      }
    },
    [queryClient],
  );
  const leaving = useRef(false);
  // SCREENS §7.7 (rev 1.77): the one rule of a stored preview, shown to this reader or not.
  const previewed = holdsStoredPreview(row);
  useEffect(() => {
    if (previewed) {
      setHadPreview(true);
    }
  }, [previewed]);

  const judgements = useQuery({
    queryKey: modificationJudgementsKey(row.id),
    queryFn: () => fetchModificationJudgements(row.id),
  });
  // A draft that was submitted before keeps its request: voided when the modification was edited, or
  // rejected where the draft revises a rejected modification (`DraftRequestNotice`).
  const request = useQuery({
    queryKey: approvalKey(row.approval_request_id ?? ""),
    queryFn: () => fetchApproval(row.approval_request_id ?? ""),
    enabled: row.approval_request_id !== null,
    retry: false,
  });
  const choices = useChangeChoices(base, true, permissions.includes(STRUCTURE_READ_PERMISSION));

  // 04 §16.14 `prefill_reasons`: the proposals of the row's latest classification. Every answer of
  // the row carries them, a read too, until an edit clears them (T-CON-06 `classification`, rev
  // 1.210).
  const reasons = useMemo(() => record(row.prefill_reasons), [row.prefill_reasons]);
  const groups = useMemo(() => questionGroups(row, reasons), [row, reasons]);
  const isClassified = Object.keys(row.proposed_treatments).length > 0;
  // Without the proposals of this row the screen cannot tell an unconfirmed proposal from a question
  // the engine does not ask. A stored preview says the row was classified as it stands; `/classify`
  // would clear it — for every reader, also when this one is not shown it — so it is not run
  // again for that alone.
  const proposalsUnknown =
    isClassified && !statesProposal(row) && openKeys(row).length > 0 && !previewed;
  const needsClassify = !isClassified || proposalsUnknown;
  const departing = departures(row.proposed_treatments, row.chosen_treatments);
  const progress: DraftProgress = {
    classified: isClassified && !proposalsUnknown,
    answersConfirmed: questionnaireConfirmed(groups),
    departs: departing.length > 0,
    judgementLinked: row.judgement_record_id !== null,
    previewed,
  };
  const step: WizardStep = stepReachable(requested, progress) ? requested : firstOpenStep(progress);
  const stale = hadPreview && !previewed;

  const stepHref = (target: WizardStep) =>
    `${location.pathname}${withParams(location.search, { [STEP_PARAM]: target })}`;
  const goTo = useCallback(
    (target: WizardStep, replace = false) => {
      void navigate(
        `${location.pathname}${withParams(location.search, { [STEP_PARAM]: target })}`,
        { replace },
      );
    },
    [location.pathname, location.search, navigate],
  );
  // The URL names the step the screen shows (SCR-URL-15).
  useEffect(() => {
    if (step !== requested) {
      goTo(step, true);
    }
  }, [step, requested, goTo]);
  // A step holds its own unsaved input and its own refusal; another step starts clean. The step is a
  // search parameter, so the shell does not move focus as it does for a route: the heading of the
  // step takes it (DS-A11Y-08, DS-A11Y-09).
  const stepHeading = useRef<HTMLHeadingElement>(null);
  const shownStep = useRef<WizardStep | null>(null);
  useEffect(() => {
    leaving.current = false;
    setDirty(false);
    setChoosing(false);
    setProblem(null);
    if (shownStep.current !== null && shownStep.current !== step) {
      stepHeading.current?.focus();
    }
    shownStep.current = step;
  }, [step]);
  /** Goes on after a save: the input of the step left is stored, so nothing is discarded. */
  const proceed = (target: WizardStep) => {
    leaving.current = true;
    goTo(target);
  };

  const blocker = useBlocker(({ currentLocation, nextLocation }) => {
    if (!dirty || leaving.current) {
      return false;
    }
    return (
      currentLocation.pathname !== nextLocation.pathname ||
      new URLSearchParams(currentLocation.search).get(STEP_PARAM) !==
        new URLSearchParams(nextLocation.search).get(STEP_PARAM)
    );
  });

  const refreshLists = () =>
    Promise.all(
      MODIFICATION_LIST_KEYS.map((queryKey) => queryClient.invalidateQueries({ queryKey })),
    );

  // The row version a classification was last asked for: it is asked once for a version.
  const classifiedFor = useRef<number | null>(null);

  /**
   * `/classify` of the row `asked`, the row as the API holds it: the proposal is stored on the row;
   * the proposed answers are kept beside it.
   */
  const classify = async (asked: Modification): Promise<boolean> => {
    setWorking("classify");
    try {
      const outcome = await classifyCommand.submit({});
      if (outcome.kind !== "succeeded" || outcome.data === null) {
        setProblem(failureOf(outcome));
        return false;
      }
      apply(rowOfClassification(outcome.data, asked));
      return true;
    } finally {
      setWorking(null);
    }
  };

  /** `PATCH`, then `/classify`: every edit clears the proposal and the stored preview (SM-03). */
  const save = async (body: ModificationUpdateBody): Promise<boolean> => {
    setWorking("save");
    setProblem(null);
    try {
      const outcome = await patch.submit(body);
      if (outcome.kind !== "succeeded" || outcome.data === null) {
        setProblem(failureOf(outcome));
        return false;
      }
      apply(outcome.data);
      // The row changed: a classification, a preview or a submission of the row before it is over.
      classifyCommand.reset();
      preview.reset();
      submitCommand.reset();
      void refreshLists();
      classifiedFor.current = outcome.data.row_version;
      return await classify(outcome.data);
    } finally {
      setWorking(null);
    }
  };

  // A step past "Change" needs the proposal of the row as it stands.
  useEffect(() => {
    if (
      requested !== "change" &&
      needsClassify &&
      working === null &&
      classifiedFor.current !== row.row_version
    ) {
      classifiedFor.current = row.row_version;
      setProblem(null);
      void classify(row);
    }
    // `classify` sends the command of this render; the effect follows the row version.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [requested, needsClassify, working, row.row_version]);

  const busy = working !== null;
  // Steps 1 and 2 send the departures the preparer made and leave the defaults to `/classify`.
  const answer = (group: QuestionGroup, question: Question, value: boolean) =>
    void save({
      questionnaire: withAnswer(row.questionnaire, group.obligationKey, question, value),
      ...choicesOf(authoredChoices(row)),
    });
  const confirm = (group: QuestionGroup, confirmed: boolean) =>
    void save({
      questionnaire: confirmed
        ? withGroupConfirmed(row.questionnaire, group)
        : withoutGroup(row.questionnaire, group),
      ...choicesOf(authoredChoices(row)),
    });

  // --- step captions (SCREENS §7.4 to §7.8) and the stepper.
  const confirmedCount = confirmedAnswers(groups);
  // The catch-up of the stored preview, which the API answers to every reader of the row.
  const catchUp = storedCatchUp(row);
  const captions: Readonly<Record<WizardStep, string | undefined>> = {
    change: `${kindLabel(row.kind)} · ${formatDate(row.effective_date)}`,
    questionnaire: t("modifications.wizard.caption.questionnaire", {
      count: confirmedCount,
      formatted: formatNumber(confirmedCount, { kind: "count" }),
    }),
    treatment: row.treatment_summary === null ? undefined : treatmentLabel(row.treatment_summary),
    preview:
      catchUp === null
        ? undefined
        : t("modifications.wizard.caption.preview", {
            amount: formatMoney(catchUp.amount, row.currency, { variant: "cell", delta: true }),
          }),
    submit: undefined,
  };
  const open = firstOpenStep(progress);
  const steps: Step[] = WIZARD_STEPS.map((id) => {
    const done = WIZARD_STEPS.indexOf(id) < WIZARD_STEPS.indexOf(open);
    return {
      id,
      label: stepLabel(id),
      state: id === step ? "current" : done ? "complete" : "pending",
      caption: done || id === step ? captions[id] : undefined,
      to: done && id !== step ? stepHref(id) : undefined,
    };
  });

  // --- the blocking line and the footer of the step shown.
  const previous = WIZARD_STEPS[WIZARD_STEPS.indexOf(step) - 1];
  const linked = (judgements.data ?? []).find((item) => item.id === row.judgement_record_id);
  const cancel = () => void navigate(`/contracts/${contract.id}/modifications${ctxSearch}`);

  const submit = async () => {
    setWorking("submit");
    setProblem(null);
    try {
      const outcome = await submitCommand.submit({
        comment: comment.trim() === "" ? null : comment.trim(),
      } satisfies ModificationSubmitBody);
      if (outcome.kind !== "succeeded") {
        setProblem(failureOf(outcome));
        return;
      }
      // SCREENS §7.8 (rev 1.42; PRD rev 1.158 J-06.5): a submission routes one request — the linked
      // estimate versions are approved and the override record is reviewed before it — and the toast
      // names that request, as every routed submission does. The read is the one the detail shows
      // its routing from.
      const submitted = outcome.data;
      const requestId = submitted?.approval_request_id ?? null;
      let request: string | null = null;
      if (requestId !== null) {
        try {
          const routed = await queryClient.fetchQuery({
            queryKey: approvalKey(requestId),
            queryFn: () => fetchApproval(requestId),
            retry: false,
          });
          request = routed.request_no;
        } catch {
          request = null;
        }
      }
      toast.show({
        tone: "positive",
        message:
          request === null
            ? t("modifications.wizard.submitted")
            : t("contracts.drawer.submittedForApproval", { request }),
      });
      leaving.current = true;
      if (submitted === null) {
        void queryClient.invalidateQueries({ queryKey: modificationKey(row.id) });
      } else {
        apply(submitted);
      }
    } finally {
      setWorking(null);
    }
  };

  // SCREENS §7.3 "Discard draft" (rev 1.26): for a holder of `modification.create` for the contract's
  // entity (§0.6 SCR-PERM-02 (a)). The API refuses it while a review of one of the modification's own
  // judgement records is pending (PRD ERR-82) and names each record; the draft then stays.
  const discard = async () => {
    setDiscardProblem(null);
    const outcome = await discardCommand.submit();
    if (outcome.kind !== "succeeded") {
      setDiscardProblem(failureOf(outcome));
      return;
    }
    toast.show({ tone: "positive", message: t("modifications.wizard.discarded") });
    // What the form holds goes with the draft: the leave is not asked about.
    leaving.current = true;
    discarded.current = outcome.data;
    setDiscarding(false);
    void navigate(`/contracts/${contract.id}/modifications${ctxSearch}`);
  };

  let content: ReactNode;
  let blocked: string | null = null;
  let next: ReactNode = null;
  // Step "Treatment" holds what "Next" saves, so it renders the footer itself.
  let ownFooter = false;
  const nextButton = (reason: string | null, onNext: () => void) => (
    <Button variant="primary" loading={busy} disabledReason={reason ?? undefined} onClick={onNext}>
      {t("modifications.wizard.next")}
    </Button>
  );

  if (step === "change") {
    content = (
      <>
        <ProblemNotice problem={problem === "unreached" ? problem : null} />
        <DraftChange
          key={row.id}
          formId={formId}
          base={base}
          row={row}
          choices={choices}
          problem={problem === "unreached" ? null : problem}
          busy={busy}
          onDirty={setDirty}
          onSave={async (body) => {
            if (dirty) {
              // A departure stays for an obligation the edited modification still names.
              const named = new Set([
                ...base.context.obligations.map((item) => item.key),
                ...(body.lines ?? []).map((line) => line.obligation_key),
              ]);
              if (!(await save({ ...body, ...choicesOf(authoredChoices(row, named)) }))) {
                return;
              }
            }
            proceed("questionnaire");
          }}
        />
        <LinkedEstimateVersions
          contract={contract}
          row={row}
          canAdd={canEstimate}
          canJudge={canJudge}
          contextPeriod={new URLSearchParams(location.search).get("period")}
          periodLabel={base.periodLabel}
          ctxSearch={ctxSearch}
        />
        <LinkedJudgements
          modificationId={row.id}
          contract={contract}
          judgements={judgements.data ?? []}
          loading={judgements.isPending}
          canAdd={canJudge}
        />
      </>
    );
    next = (
      <Button type="submit" form={formId} variant="primary" loading={busy}>
        {t("modifications.wizard.next")}
      </Button>
    );
  } else if (step === "questionnaire") {
    blocked =
      progress.classified && progress.answersConfirmed
        ? null
        : t("modifications.wizard.questionnaire.blocked");
    content = (
      <QuestionnaireStep
        row={row}
        base={base}
        groups={groups}
        loading={needsClassify && problem === null}
        busy={busy}
        problem={problem}
        onRetry={
          needsClassify && !busy
            ? () => {
                setProblem(null);
                void classify(row);
              }
            : undefined
        }
        onAnswer={answer}
        onConfirm={confirm}
      />
    );
    next = nextButton(blocked, () => goTo("treatment"));
  } else if (step === "treatment") {
    content = (
      <TreatmentStep
        key={row.row_version}
        row={row}
        base={base}
        linked={linked ?? null}
        problem={problem}
        busy={busy}
        legacyAllowed={permissions.includes(STRUCTURE_READ_PERMISSION)}
        canRecord={canJudge}
        onDirty={setDirty}
        onDeparting={setChoosing}
        onSave={save}
        onNext={() => proceed("preview")}
        onBack={() => goTo("questionnaire")}
      />
    );
    ownFooter = true;
  } else if (step === "preview") {
    blocked = previewed ? null : t("modifications.wizard.preview.blocked");
    content = (
      <PreviewStep
        row={row}
        base={base}
        command={preview}
        contextPeriod={new URLSearchParams(location.search).get("period")}
      />
    );
    next = nextButton(blocked, () => goTo("submit"));
  } else {
    blocked = submitBlocked(row, departing, linked, judgements.data ?? []);
    content = (
      <SubmitStep
        row={row}
        judgements={judgements.data ?? []}
        departing={departing}
        comment={comment}
        onComment={setComment}
        problem={problem}
        busy={busy}
      />
    );
    next = (
      <Button
        variant="primary"
        loading={working === "submit"}
        disabledReason={blocked ?? undefined}
        onClick={() => void submit()}
      >
        {t("modifications.wizard.submit")}
      </Button>
    );
  }

  return (
    <ModificationFrame
      testId="SF-07-page"
      contract={contract}
      ctxSearch={ctxSearch}
      title={t("modifications.wizard.title.new")}
      reference={row.reference ?? row.modification_no}
      status={row.status}
      override={departing.length > 0 || (step === "treatment" && choosing)}
      actions={
        canDiscard ? (
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              setDiscardProblem(null);
              setDiscarding(true);
            }}
          >
            {t("modifications.wizard.discard")}
          </Button>
        ) : undefined
      }
    >
      <div data-testid="SF-07-stepper">
        <Stepper label={t("modifications.wizard.stepper")} steps={steps} currentId={step} />
      </div>
      {/* SCREENS §7.10 "Voided request (stale)" and "Revised draft". */}
      <DraftRequestNotice request={request.data} ctxSearch={ctxSearch} />
      {stale ? (
        <Banner
          tone="warning"
          title={t("modifications.wizard.preview.stale")}
          announce="live"
          headingLevel={2}
          actions={
            step === "preview" ? undefined : (
              <Button
                variant="link"
                disabledReason={
                  stepReachable("preview", progress)
                    ? undefined
                    : t("modifications.wizard.preview.notYet")
                }
                onClick={() => goTo("preview")}
              >
                {t("modifications.wizard.preview.run")}
              </Button>
            )
          }
        />
      ) : null}
      <section aria-labelledby={`${formId}-step`} className="flex flex-1 flex-col gap-4">
        <h2
          ref={stepHeading}
          id={`${formId}-step`}
          tabIndex={-1}
          className="text-title-md text-fg-1"
        >
          {stepLabel(step)}
        </h2>
        {content}
        {ownFooter ? null : (
          <WizardFooter
            blocked={blocked}
            back={
              previous === undefined
                ? { label: t("contracts.draft.cancel"), onBack: cancel }
                : { label: t("modifications.wizard.back"), onBack: () => goTo(previous) }
            }
            next={next}
          />
        )}
      </section>
      <Modal
        open={blocker.state === "blocked"}
        variant="confirmation"
        title={t("common.dialog.discard.title")}
        description={t("common.dialog.discard.description")}
        primaryAction={{
          label: t("common.dialog.discard.confirm"),
          destructive: true,
          onAction: () => {
            setDirty(false);
            blocker.proceed?.();
          },
        }}
        onClose={() => blocker.reset?.()}
      />
      <Modal
        open={discarding}
        variant="confirmation"
        title={t("modifications.wizard.discardTitle")}
        description={t("modifications.wizard.discardDescription")}
        primaryAction={{
          label: t("modifications.wizard.discard"),
          destructive: true,
          onAction: () => void discard(),
        }}
        submitting={discardCommand.pending}
        onClose={() => setDiscarding(false)}
        testId="SF-07-dialog-discard"
      >
        <ProblemNotice problem={discardProblem} />
      </Modal>
    </ModificationFrame>
  );
}

// ---------------------------------------------------------------------------------------------------
// Step 1 of a draft: the general form, seeded from the row.

function DraftChange({
  formId,
  base,
  row,
  choices,
  problem,
  busy,
  onDirty,
  onSave,
}: {
  readonly formId: string;
  readonly base: WizardBase;
  readonly row: Modification;
  readonly choices: ReturnType<typeof useChangeChoices>;
  readonly problem: ApiProblem | null;
  readonly busy: boolean;
  readonly onDirty: (dirty: boolean) => void;
  readonly onSave: (body: ModificationUpdateBody) => void | Promise<void>;
}) {
  // Seeded once: a save re-seeds through the row id only when another draft opens.
  const [variant] = useState<ChangeVariant>(() => ({
    kind: "general",
    initial: changeFromModification(row, (index) => `l${String(index + 1)}`),
  }));
  if (choices.error !== null) {
    return (
      <LoadError
        title={t("contracts.draft.loadError")}
        problem={choices.error}
        onRetry={choices.retry}
      />
    );
  }
  if (choices.loading) {
    return <Skeleton region={t("modifications.wizard.steps.change")} shape="rows" count={6} />;
  }
  return (
    <ChangeStep
      formId={formId}
      variant={variant}
      context={base.context}
      obligationChoices={base.obligationChoices}
      products={choices.products}
      entities={choices.entities}
      latestEvent={choices.latestEvent}
      problem={problem}
      busy={busy}
      onDirty={onDirty}
      onBuilt={(body) =>
        void onSave({
          kind: body.kind,
          reference: body.reference ?? null,
          effective_date: body.effective_date,
          // `PATCH` leaves a member it is not sent and clears a nullable one sent as null (04 §16.14
          // rev 1.188, item MOD-PATCH-CLEAR-1): an emptied scope description and the amount of a
          // price change whose kind became another are sent as null.
          rationale: body.rationale ?? null,
          lines: body.lines,
          price_change_amount: body.price_change_amount ?? null,
        } satisfies ModificationUpdateBody)
      }
    />
  );
}

// ---------------------------------------------------------------------------------------------------
// Linked judgement records (SCREENS §7.4; BR-MOD-02).

const TOPIC_KEY = "modifications.judgement.topic";

function topicLabel(topic: string): string {
  const key = `${TOPIC_KEY}.${topic}`;
  return hasMessage(key) ? t(key) : topic;
}

function LinkedJudgements({
  modificationId,
  contract,
  judgements,
  loading,
  canAdd,
}: {
  readonly modificationId: string;
  /** The modification's contract: the entity and the hold a record's discard reads. */
  readonly contract: RecordContract;
  readonly judgements: readonly Judgement[];
  readonly loading: boolean;
  /** `judgement.create` (BR-UX-05): the button renders only for a holder. */
  readonly canAdd: boolean;
}) {
  const [adding, setAdding] = useState(false);
  const headingId = useId();
  // SCREENS §7.4 (rev 1.66): a draft the judgement drawer left behind — its submission was refused
  // and the drawer was closed — holds the modification's own submission (PRD ERR-95). Its row
  // carries "Discard"; the column stands only while a row has the command. A rejected record's row
  // carries it too (rev 1.74; PRD SM-10 rev 1.199): the record a new one replaced leaves this way.
  const discards = useRecordDiscard(contract);
  const actions = judgements.some(discards)
    ? (record: Judgement) => (
        <DiscardRecord
          record={record}
          contract={contract}
          invalidates={[modificationJudgementsKey(modificationId)]}
          testId="SF-07-dialog-discard-record"
        />
      )
    : undefined;
  return (
    <section aria-labelledby={headingId} className="flex flex-col gap-2">
      <div className="flex flex-wrap items-center gap-3">
        <h3 id={headingId} className="text-title-sm text-fg-1">
          {t("modifications.wizard.linked.judgements")}
        </h3>
        <span className="flex-1" />
        {canAdd ? (
          <Button variant="secondary" size="sm" onClick={() => setAdding(true)}>
            {t("modifications.wizard.linked.add")}
          </Button>
        ) : null}
      </div>
      {loading ? (
        <Skeleton region={t("modifications.wizard.linked.judgements")} shape="rows" count={2} />
      ) : judgements.length === 0 ? (
        <p className="text-body-sm text-fg-2">{t("modifications.wizard.linked.none")}</p>
      ) : (
        <JudgementTable judgements={judgements} labelledBy={headingId} actions={actions} />
      )}
      {adding ? (
        <JudgementDrawer
          modificationId={modificationId}
          topics={LINKED_TOPICS}
          onClose={() => setAdding(false)}
          onRecorded={() => setAdding(false)}
        />
      ) : null}
    </section>
  );
}

/**
 * SCREENS §7.4 "Linked judgement records": Topic, Conclusion, Status; the record number under the
 * topic. `actions` adds the column "Actions" with what it answers for a row (rev 1.66: "Discard" on
 * a draft, in the wizard); the read-only detail passes none.
 */
export function JudgementTable({
  judgements,
  labelledBy,
  actions,
}: {
  readonly judgements: readonly Judgement[];
  readonly labelledBy: string;
  readonly actions?: ((record: Judgement) => ReactNode) | undefined;
}) {
  return (
    <table
      aria-labelledby={labelledBy}
      data-testid="SF-07-grid-judgements"
      className="w-full border-collapse text-body-sm"
    >
      <thead>
        <tr className="border-b border-default text-caption text-fg-3">
          {(["topic", "conclusion", "status"] as const).map((column) => (
            <th key={column} scope="col" className="px-2 py-1.5 text-start font-medium">
              {t(`modifications.wizard.linked.column.${column}`)}
            </th>
          ))}
          {actions === undefined ? null : (
            <th scope="col" className="px-2 py-1.5 text-start font-medium">
              {t("contracts.workbench.step1.column.actions")}
            </th>
          )}
        </tr>
      </thead>
      <tbody>
        {judgements.map((item) => (
          <tr key={item.id} className="border-b border-hairline align-top">
            <th scope="row" className="px-2 py-1.5 text-start font-medium text-fg-1">
              <span className="flex flex-col">
                <span>{topicLabel(item.topic)}</span>
                <span className="font-mono text-mono-sm font-normal text-fg-3">
                  {item.judgement_no}
                </span>
              </span>
            </th>
            <td className="px-2 py-1.5">{item.conclusion}</td>
            <td className="px-2 py-1.5">{judgementStatusLabel(item.status)}</td>
            {actions === undefined ? null : <td className="px-2 py-1.5">{actions(item)}</td>}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

interface JudgementDrawerProps {
  readonly modificationId: string;
  /** One topic: the override record of step "Treatment"; several: the linked panel's select. */
  readonly topics: readonly JudgementTopic[];
  readonly onClose: () => void;
  /** The record is created and submitted for review. */
  readonly onRecorded: (judgement: Judgement) => void | Promise<void>;
}

type JudgementUpdateBody = components["schemas"]["JudgementUpdateIn"];

/**
 * A judgement record whose subject is the modification: created, then submitted for review (two
 * commands of one press; SCREENS §4.9.1 pattern). A record whose submission did not go through is
 * kept: the next press corrects that draft and submits it, so no second record is created.
 */
function JudgementDrawer({ modificationId, topics, onClose, onRecorded }: JudgementDrawerProps) {
  const queryClient = useQueryClient();
  const toast = useToast();
  // The keys of the record's create, change and submission (DG-FE-05 rev 1.156): a press repeated
  // after a lost answer sends the command under the key it had, and the API replays its answer.
  const keys = useCommandKeys();
  const formId = useId();
  const [topic, setTopic] = useState<JudgementTopic | null>(
    topics.length === 1 ? (topics[0] ?? null) : null,
  );
  const [conclusion, setConclusion] = useState("");
  const [rationale, setRationale] = useState("");
  const [references, setReferences] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [problem, setProblem] = useState<Failure | null>(null);
  // The draft of this drawer whose submission is still owed, with the content it holds.
  const [draft, setDraft] = useState<{
    readonly record: Judgement;
    readonly content: string;
  } | null>(null);

  const errors = {
    topic: topic === null ? t("modifications.judgement.error.topic") : null,
    conclusion: conclusion.trim() === "" ? t("modifications.judgement.error.conclusion") : null,
    rationale: rationale.trim() === "" ? t("modifications.judgement.error.rationale") : null,
  };
  const submit = async () => {
    setAttempted(true);
    if (topic === null || errors.conclusion !== null || errors.rationale !== null) {
      return;
    }
    const authored = {
      conclusion: conclusion.trim(),
      rationale: rationale.trim(),
      codification_refs: references
        .split(",")
        .map((item) => item.trim())
        .filter((item) => item !== ""),
    };
    const content = JSON.stringify(authored);
    setSubmitting(true);
    setProblem(null);
    try {
      let record = draft?.record ?? null;
      if (record === null) {
        const created = await sendCommand<Judgement>(keys, "POST", JUDGEMENTS_PATH, {
          topic,
          subject_type: MODIFICATION_SUBJECT,
          subject_id: modificationId,
          ...authored,
        } satisfies JudgementCreateBody);
        if (!created.ok) {
          setProblem(created.problem);
          return;
        }
        record = created.data;
        setDraft({ record, content });
        void queryClient.invalidateQueries({ queryKey: modificationJudgementsKey(modificationId) });
      } else if (draft?.content !== content) {
        const updated = await sendCommand<Judgement>(
          keys,
          "PATCH",
          `${JUDGEMENTS_PATH}/${record.id}`,
          authored satisfies JudgementUpdateBody,
        );
        if (!updated.ok) {
          setProblem(updated.problem);
          return;
        }
        record = updated.data;
        setDraft({ record, content });
      }
      const submitted = await sendCommand<Judgement>(
        keys,
        "POST",
        `${JUDGEMENTS_PATH}/${record.id}/submit`,
        { comment: null },
      );
      if (!submitted.ok) {
        setProblem(submitted.problem);
        return;
      }
      await queryClient.invalidateQueries({ queryKey: modificationJudgementsKey(modificationId) });
      toast.show({
        tone: "positive",
        message: t("modifications.judgement.recorded", { number: record.judgement_no }),
      });
      await onRecorded(submitted.data);
    } catch {
      // The request did not reach the server or its answer was lost.
      setProblem("unreached");
    } finally {
      setSubmitting(false);
    }
  };
  const shown = (name: keyof typeof errors) => (attempted ? errors[name] : null);
  // The topic of a record that exists is its own (04 T-CON-19: `PATCH` does not change it).
  const fixedTopic = topics.length === 1 ? (topics[0] ?? null) : draft === null ? null : topic;

  return (
    <Drawer
      open
      title={t("modifications.judgement.title")}
      initialFocus="field"
      dirty={conclusion !== "" || rationale !== "" || references !== ""}
      submitting={submitting}
      banner={<ProblemNotice problem={problem} />}
      primaryAction={{ label: t("modifications.judgement.save"), form: formId }}
      onClose={onClose}
    >
      <form
        id={formId}
        noValidate
        data-testid="SF-07-drawer-judgement"
        className="flex flex-col gap-4"
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        {fixedTopic !== null ? (
          <dl className="flex flex-col gap-0.5">
            <dt className="text-caption text-fg-3">{t("modifications.judgement.topic")}</dt>
            <dd className="text-body text-fg-1">{topicLabel(fixedTopic)}</dd>
          </dl>
        ) : (
          <Field
            name="judgement-topic"
            label={t("modifications.judgement.topic")}
            required
            error={shown("topic")}
            width="text"
          >
            {(control) => (
              <Select<JudgementTopic>
                control={control}
                options={topics.map((value) => ({ value, label: topicLabel(value) }))}
                value={topic}
                onChange={setTopic}
                invalid={shown("topic") !== null}
              />
            )}
          </Field>
        )}
        <TextField
          name="judgement-conclusion"
          label={t("modifications.judgement.conclusion")}
          required
          multiline
          value={conclusion}
          onChange={setConclusion}
          error={shown("conclusion")}
        />
        <TextField
          name="judgement-rationale"
          label={t("modifications.judgement.rationale")}
          required
          multiline
          value={rationale}
          onChange={setRationale}
          error={shown("rationale")}
        />
        <TextField
          name="judgement-references"
          label={t("modifications.judgement.references")}
          optional
          help={t("modifications.judgement.referencesHelp")}
          value={references}
          onChange={setReferences}
        />
      </form>
    </Drawer>
  );
}

// ---------------------------------------------------------------------------------------------------
// Step 2: Questionnaire (SCREENS §7.5).

const QUESTION_HELP: Readonly<Record<Question, string>> = {
  added_goods_distinct: "modifications.question.added_goods_distinct.help",
  priced_at_ssp: "modifications.question.priced_at_ssp.help",
  remaining_goods_distinct_from_transferred:
    "modifications.question.remaining_goods_distinct_from_transferred.help",
};

const ATTESTED = "modifications.prefill.priced_at_ssp.attested";

/**
 * The catalogue key of a reading's sentence: its `reason_key`, but for `attested` — the engine
 * passed the price test on the preparer's answer and compared nothing (04 §16.14 rev 1.250) — one of
 * three forms of the one reason: the price beside the range, beside the point, or alone where no SSP
 * entry resolves. The sentence states the figures and concludes nothing from them.
 */
function captionKey(reading: Prefill): string {
  if (reading.reasonKey !== ATTESTED) {
    return reading.reasonKey;
  }
  const stated = (name: string) => (reading.params[name] ?? "") !== "";
  if (stated("low") && stated("high")) {
    return ATTESTED;
  }
  return stated("point") ? `${ATTESTED}Point` : `${ATTESTED}NoSsp`;
}

/**
 * The catalogue text of a reading's `reason_key` with its `params`; null where the catalogue has no
 * sentence for it. `version` is the label of the SSP book version the price was tested against; the
 * engine's version key stands in for it.
 */
export function readingCaption(
  reading: Prefill,
  currency: string,
  version?: string,
): string | null {
  const amount = (name: string) => {
    const value = reading.params[name];
    return value === undefined || !/^-?\d+(?:\.\d+)?$/.test(value)
      ? (value ?? "")
      : formatMoney(value, currency, { variant: "cell" });
  };
  const progress = reading.params.progress;
  const params = {
    price: amount("price"),
    low: amount("low"),
    high: amount("high"),
    point: amount("point"),
    version: version ?? (reading.params.ssp_version_key ?? "").replace("@v", " v"),
    progress: progress === undefined || progress === "" ? "" : formatPercent(progress),
  };
  const key = captionKey(reading);
  return hasMessage(key) ? t(key, params) : null;
}

/** The caption of a proposed answer; a reason the catalogue does not know reads as a proposal. */
export function prefillCaption(prefill: Prefill, currency: string, version?: string): string {
  return readingCaption(prefill, currency, version) ?? t("modifications.prefill.other");
}

/**
 * Whether the stored SSP basis of a line is the version the reading's price test read. The engine
 * names that version by `<book code>@v<version no>` (`params.ssp_version_key`). The basis is that
 * version while it is the classification's default, and may be another once the preparer names a
 * version for the allocation ("Use another approved SSP version", `is_override`): the figures of
 * the test are then not that version's, and are neither printed beside its label nor named by it.
 * A basis whose version cannot be read (no `ssp.read`) is taken for the tested one unless it is an
 * override.
 */
export function isTestedVersion(
  label: SspVersionLabel,
  override: boolean,
  reading: Prefill,
): boolean {
  const tested = reading.params.ssp_version_key ?? "";
  if (tested === "") {
    return false;
  }
  return label.key === null ? !override : label.key === tested;
}

/**
 * The range of a price test, written "<low> to <high>" (every catalogue message carries a word), or
 * its point for an entry with a point; null where the test states neither (SCREENS §7.6).
 */
export function priceRange(test: PriceTest, currency: string): string | null {
  const params: Readonly<Record<string, string | undefined>> = test.params;
  const money = (value: string | undefined) =>
    value !== undefined && /^-?\d+(?:\.\d+)?$/.test(value)
      ? formatMoney(value, currency, { variant: "cell" })
      : null;
  const from = money(params.low);
  const to = money(params.high);
  if (from !== null && to !== null) {
    return t("modifications.wizard.treatment.range", { low: from, high: to });
  }
  return money(params.point);
}

/**
 * The sentence under an answer, with the SSP version by its label once that is read: the reason of
 * a proposal, or — `fact` — the engine's price test beside a stored answer, which is no proposal and
 * shows nothing where the catalogue has no sentence for its reason. The label is that of the line's
 * stored basis while that is the version the test read (`isTestedVersion`); else the engine's key
 * names the version.
 */
function PrefillLine({
  prefill,
  fact = false,
  currency,
  versionId,
  override,
  as: Tag = "p",
  className = "text-body-sm text-fg-2",
}: {
  readonly prefill: Prefill;
  readonly fact?: boolean;
  readonly currency: string;
  readonly versionId: string | null;
  /** The stored basis is a version the preparer named (`ssp_basis[key].is_override`). */
  readonly override: boolean;
  /** A paragraph under a question of the wizard; a description in a list on SF-07:detail. */
  readonly as?: "p" | "dd";
  readonly className?: string;
}) {
  const label = useQuery({
    queryKey: sspVersionLabelKey(versionId ?? ""),
    queryFn: () => fetchSspVersionLabel(versionId ?? "", null),
    enabled: versionId !== null && prefill.params.ssp_version_key !== undefined,
    retry: false,
  });
  const version =
    label.data === undefined ||
    label.data.label === "" ||
    !isTestedVersion(label.data, override, prefill)
      ? undefined
      : label.data.label;
  const text = fact
    ? readingCaption(prefill, currency, version)
    : prefillCaption(prefill, currency, version);
  return text === null ? null : <Tag className={className}>{text}</Tag>;
}

/**
 * The sentence of the price test a row states for an added line, as a fact beside the answer of
 * `priced_at_ssp` (SCREENS §7.5; on SF-07:detail §7.9); nothing where the row states none.
 */
export function PriceTestLine({
  row,
  obligationKey,
  as,
  className,
}: {
  readonly row: Modification;
  readonly obligationKey: string;
  readonly as?: "p" | "dd";
  readonly className?: string;
}) {
  const test = priceTestOf(row, obligationKey);
  if (test === null) {
    return null;
  }
  const basis = basisOf(record(row.ssp_basis)[obligationKey]);
  return (
    <PrefillLine
      prefill={test}
      fact
      currency={row.currency}
      versionId={basis.versionId}
      override={basis.override}
      {...(as === undefined ? {} : { as })}
      {...(className === undefined ? {} : { className })}
    />
  );
}

function groupHeading(row: Modification, base: WizardBase, key: string): string {
  const existing = base.obligations.find((item) => item.obligation_key === key);
  if (existing !== undefined) {
    return [
      `${key} ${existing.product.code}`,
      existing.current.quantity === null ? null : formatNumber(existing.current.quantity),
      dateRange(existing.start_date, existing.end_date),
    ]
      .filter((part): part is string => part !== null)
      .join(" · ");
  }
  const line = row.lines.map(record).find((item) => item.obligation_key === key) ?? {};
  const text = (value: unknown) => (typeof value === "string" && value !== "" ? value : null);
  const date = (value: unknown) => {
    const parsed = typeof value === "string" ? parseDateInput(value) : null;
    return parsed !== null && parsed.ok ? parsed.value : null;
  };
  const product = text(line.product_code);
  const quantity = text(line.quantity_delta);
  return [
    product === null ? key : `${key} ${product}`,
    quantity === null ? null : formatNumber(quantity),
    dateRange(date(line.start_date), date(line.end_date)),
  ]
    .filter((part): part is string => part !== null)
    .join(" · ");
}

function QuestionnaireStep({
  row,
  base,
  groups,
  loading,
  busy,
  problem,
  onRetry,
  onAnswer,
  onConfirm,
}: {
  readonly row: Modification;
  readonly base: WizardBase;
  readonly groups: readonly QuestionGroup[];
  readonly loading: boolean;
  readonly busy: boolean;
  readonly problem: Failure | null;
  /** The classification did not answer: asks for it again. */
  readonly onRetry: (() => void) | undefined;
  readonly onAnswer: (group: QuestionGroup, question: Question, value: boolean) => void;
  readonly onConfirm: (group: QuestionGroup, confirmed: boolean) => void;
}) {
  const name = useId();
  if (loading && groups.length === 0) {
    return (
      <Skeleton region={t("modifications.wizard.steps.questionnaire")} shape="rows" count={6} />
    );
  }
  return (
    <div
      className="flex max-w-[var(--content-max-form)] flex-col gap-6"
      aria-busy={busy || undefined}
    >
      <ProblemNotice problem={problem} onRetry={onRetry} />
      {groups.length === 0 && problem === null ? (
        <p className="text-body-sm text-fg-2">{t("modifications.wizard.questionnaire.none")}</p>
      ) : null}
      {groups.map((group) => {
        const answered = group.questions.every((item) => item.value !== null);
        const confirmId = `${name}-${group.obligationKey}-confirm`;
        return (
          <section
            key={group.obligationKey}
            aria-labelledby={`${name}-${group.obligationKey}-heading`}
            data-testid={`SF-07-group-${group.obligationKey}`}
            className="flex flex-col gap-3 rounded-lg border border-hairline bg-surface p-[var(--panel-pad)]"
          >
            <h3 id={`${name}-${group.obligationKey}-heading`} className="text-title-sm text-fg-1">
              {groupHeading(row, base, group.obligationKey)}
            </h3>
            {group.questions.map((item) => {
              const legendId = `${name}-${group.obligationKey}-${item.question}`;
              return (
                <fieldset
                  key={item.question}
                  role="radiogroup"
                  aria-labelledby={legendId}
                  aria-describedby={`${legendId}-help`}
                  disabled={busy}
                  className="flex flex-col gap-1"
                >
                  <legend id={legendId} className="text-body-sm font-medium text-fg-1">
                    {t(`modifications.question.${item.question}.label`)}
                  </legend>
                  <div className="flex flex-wrap items-center gap-4">
                    {[true, false].map((value) => (
                      <label
                        key={String(value)}
                        className="flex items-center gap-2 text-body text-fg-1"
                      >
                        <input
                          type="radio"
                          name={legendId}
                          checked={item.value === value}
                          onChange={() => onAnswer(group, item.question, value)}
                        />
                        {t(value ? "contracts.drawer.yes" : "contracts.drawer.no")}
                      </label>
                    ))}
                    {item.prefill === null ? null : (
                      <span className="text-caption text-fg-3">
                        {t("modifications.wizard.questionnaire.prefilled")}
                      </span>
                    )}
                  </div>
                  {item.prefill !== null ? (
                    <PrefillLine
                      prefill={item.prefill}
                      currency={row.currency}
                      versionId={basisOf(record(row.ssp_basis)[group.obligationKey]).versionId}
                      override={basisOf(record(row.ssp_basis)[group.obligationKey]).override}
                    />
                  ) : item.priceTest !== null ? (
                    // SCREENS §7.5 (rev 1.52): the engine's price test stays under a stored answer.
                    <PriceTestLine row={row} obligationKey={group.obligationKey} />
                  ) : null}
                  <p id={`${legendId}-help`} className="text-caption text-fg-3">
                    {t(QUESTION_HELP[item.question])}
                  </p>
                </fieldset>
              );
            })}
            <label
              htmlFor={confirmId}
              className="flex items-center gap-2 text-body-sm font-medium text-fg-1"
            >
              <input
                id={confirmId}
                type="checkbox"
                className="size-4"
                checked={group.confirmed}
                disabled={busy || !answered}
                onChange={(event) => onConfirm(group, event.target.checked)}
              />
              {t("modifications.wizard.questionnaire.confirm", { key: group.obligationKey })}
            </label>
          </section>
        );
      })}
      {row.treatment_summary === null ? null : (
        <p className="text-body text-fg-1">
          {t("modifications.wizard.questionnaire.proposed", {
            treatment: treatmentLabel(row.treatment_summary),
          })}
        </p>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------
// Step 3: Treatment (SCREENS §7.6).

interface BasisEdit {
  readonly override: boolean;
  readonly versionId: string | null;
  readonly justification: string;
}

function basisOf(value: unknown): { readonly versionId: string | null } & BasisEdit {
  const item = record(value);
  return {
    override: item.is_override === true,
    versionId: typeof item.ssp_book_version_id === "string" ? item.ssp_book_version_id : null,
    justification: typeof item.justification === "string" ? item.justification : "",
  };
}

/**
 * SCREENS §7.6 "SSP basis": the label of the line's stored basis and, beside it, the range or the
 * point of the engine's price test — while the basis is the version that test read. Beside a version
 * the preparer named instead, the label stands alone: the figures of the test are not its.
 */
function SspBasisLabel({
  versionId,
  override,
  test,
  currency,
}: {
  readonly versionId: string;
  readonly override: boolean;
  /** The price test the row states for the line (`price_tests`); null where it states none. */
  readonly test: PriceTest | null;
  readonly currency: string;
}) {
  const label = useQuery({
    queryKey: sspVersionLabelKey(versionId),
    queryFn: () => fetchSspVersionLabel(versionId, null),
  });
  if (label.data === undefined) {
    return <NoValue />;
  }
  const text =
    label.data.label === "" ? t("modifications.wizard.treatment.sspVersion") : label.data.label;
  const range =
    test !== null && isTestedVersion(label.data, override, test)
      ? priceRange(test, currency)
      : null;
  return <>{range === null ? text : `${text} · ${range}`}</>;
}

function TreatmentStep({
  row,
  base,
  linked,
  problem,
  busy,
  legacyAllowed,
  canRecord,
  onDirty,
  onDeparting,
  onSave,
  onNext,
  onBack,
}: {
  readonly row: Modification;
  readonly base: WizardBase;
  readonly linked: Judgement | null;
  readonly problem: Failure | null;
  readonly busy: boolean;
  readonly legacyAllowed: boolean;
  /** `judgement.create` (BR-UX-05): "Record judgement" renders only for a holder. */
  readonly canRecord: boolean;
  readonly onDirty: (dirty: boolean) => void;
  /** A choice shown departs from the proposal, saved or not. */
  readonly onDeparting: (departing: boolean) => void;
  readonly onSave: (body: ModificationUpdateBody) => Promise<boolean>;
  readonly onNext: () => void;
  readonly onBack: () => void;
}) {
  const keys = useMemo(
    () =>
      Object.keys(row.proposed_treatments).sort((left, right) =>
        left.localeCompare(right, undefined, { numeric: true }),
      ),
    [row.proposed_treatments],
  );
  // One choice per obligation of the proposal; a stored choice of a key the proposal no longer holds
  // is not carried on.
  const [chosen, setChosen] = useState<Readonly<Record<string, string>>>(() =>
    Object.fromEntries(
      Object.entries(row.proposed_treatments).map(([key, proposed]) => [
        key,
        row.chosen_treatments[key] ?? proposed,
      ]),
    ),
  );
  // `/submit` reads such a choice as a departure (REQ-MOD-002), so "Next" stores the choices shown.
  const leftover = Object.keys(row.chosen_treatments).some(
    (key) => row.proposed_treatments[key] === undefined,
  );
  const [basis, setBasis] = useState<Readonly<Record<string, BasisEdit>>>(() =>
    Object.fromEntries(
      Object.entries(record(row.ssp_basis)).map(([key, value]) => [key, basisOf(value)]),
    ),
  );
  const [recording, setRecording] = useState(false);
  const errorId = useId();
  const legacy = useQuery({
    queryKey: routeSelectionKey(base.contract.contracting_entity.code),
    queryFn: () => fetchLegacyRoute(base.contract.contracting_entity.code),
    enabled: legacyAllowed,
    retry: false,
  });
  const versions = useQuery({
    queryKey: approvedSspVersionsKey(row.currency),
    queryFn: () => fetchApprovedSspVersions(row.currency),
    retry: false,
  });
  // SCREENS §7.6: the `LEGACY_*` literals only under POL-100 `USER_SELECTED_TEMPLATE`; a treatment the
  // row already names stays a choice.
  const offered = useMemo((): readonly ModificationTreatment[] => {
    const named = [...Object.values(row.proposed_treatments), ...Object.values(chosen)];
    return [
      ...TREATMENTS,
      ...LEGACY_TREATMENTS.filter((treatment) => legacy.data === true || named.includes(treatment)),
    ];
  }, [legacy.data, row.proposed_treatments, chosen]);

  const storedBasis = record(row.ssp_basis);
  const dirty =
    keys.some(
      (key) => chosen[key] !== (row.chosen_treatments[key] ?? row.proposed_treatments[key]),
    ) ||
    Object.entries(basis).some(([key, edit]) => {
      const stored = basisOf(storedBasis[key]);
      return (
        edit.override !== stored.override ||
        (edit.override &&
          (edit.versionId !== stored.versionId || edit.justification !== stored.justification))
      );
    });
  useEffect(() => onDirty(dirty), [dirty, onDirty]);

  const departing = departures(row.proposed_treatments, chosen);
  const departs = departing.length > 0;
  useEffect(() => onDeparting(departs), [departs, onDeparting]);
  const basisErrors = Object.fromEntries(
    Object.entries(basis).flatMap(([key, edit]) => {
      if (!edit.override) {
        return [];
      }
      if (edit.versionId === null) {
        return [[key, t("modifications.wizard.treatment.error.version")]];
      }
      return edit.justification.trim() === ""
        ? [[key, t("modifications.wizard.treatment.error.justification")]]
        : [];
    }),
  ) as Readonly<Record<string, string>>;
  const [attempted, setAttempted] = useState(false);

  /** The members step 3 authors: the treatments and the SSP versions the preparer names instead. */
  const body = (judgementId?: string): ModificationUpdateBody => ({
    chosen_treatments: Object.fromEntries(
      keys.flatMap((key) => {
        const value = chosen[key];
        return value !== undefined && isTreatment(value, offered) ? [[key, value]] : [];
      }),
    ),
    ssp_basis: Object.fromEntries(
      Object.entries(basis).flatMap(([key, edit]) =>
        edit.override && edit.versionId !== null
          ? [
              [
                key,
                {
                  ssp_book_version_id: edit.versionId,
                  is_override: true,
                  justification: edit.justification.trim(),
                } satisfies SspBasisBody,
              ],
            ]
          : [],
      ),
    ),
    // A record explains a departure. Once every choice is the proposal again the save takes the
    // record off the row: `PATCH` clears a nullable member sent as null (item MOD-PATCH-CLEAR-1).
    ...(judgementId !== undefined
      ? { judgement_record_id: judgementId }
      : departing.length === 0 && row.judgement_record_id !== null
        ? { judgement_record_id: null }
        : {}),
  });

  // A record explains a departure while it is sent for review or reviewed (SCREENS §7.6, rev 1.66).
  // A rejected and a discarded one explain nothing: a new record takes their place, and the banner
  // keeps naming the old one with its status. A draft explains nothing either and holds the
  // modification's submission (PRD ERR-95): it is discarded first, then a new one is recorded.
  const unexplained =
    row.judgement_record_id === null || (linked !== null && !recordStands(linked.status));
  const discardsDraft = useRecordDiscard(base.contract);
  const needsJudgement = departing.length > 0 && unexplained;
  const blocked = needsJudgement ? t("modifications.wizard.treatment.blocked") : null;
  const goOn = () => {
    setAttempted(true);
    if (Object.keys(basisErrors).length > 0) {
      return;
    }
    if (!dirty && !leftover) {
      onNext();
      return;
    }
    void onSave(body()).then((saved) => {
      if (saved) {
        onNext();
      }
    });
  };

  const versionOptions: readonly SspVersionChoice[] = versions.data ?? [];

  return (
    <div className="flex flex-1 flex-col gap-4">
      <ProblemNotice problem={problem} />
      {departing.length === 0 ? null : (
        <div data-testid="SF-07-banner-override" role="status">
          <Banner
            tone="warning"
            title={t("modifications.wizard.override.banner")}
            announce="static"
            headingLevel={3}
            actions={
              linked !== null && linked.status === "DRAFT" ? (
                discardsDraft(linked) ? (
                  <DiscardRecord
                    record={linked}
                    contract={base.contract}
                    invalidates={[modificationJudgementsKey(row.id)]}
                    testId="SF-07-dialog-discard-record"
                  />
                ) : undefined
              ) : unexplained && canRecord ? (
                <Button variant="link" onClick={() => setRecording(true)}>
                  {t("modifications.wizard.override.record")}
                </Button>
              ) : undefined
            }
          >
            {linked === null ? null : (
              <p>
                {t("modifications.wizard.override.linked", {
                  number: linked.judgement_no,
                  status: judgementStatusLabel(linked.status),
                })}
              </p>
            )}
            {unexplained && !canRecord ? (
              <p>
                {t("settings.access.description", {
                  permission: t("modifications.access.judgements"),
                })}
              </p>
            ) : null}
          </Banner>
        </div>
      )}
      <div className="overflow-x-auto">
        <table data-testid="SF-07-grid-treatments" className="w-full border-collapse text-body-sm">
          <caption className="pb-2 text-start text-title-sm text-fg-1">
            {t("modifications.wizard.treatment.caption")}
          </caption>
          <thead>
            <tr className="border-b border-default text-caption text-fg-3">
              {(["obligation", "proposed", "chosen", "sspBasis", "override"] as const).map(
                (column) => (
                  <th key={column} scope="col" className="px-2 py-1.5 text-start font-medium">
                    {t(`modifications.wizard.treatment.column.${column}`)}
                  </th>
                ),
              )}
            </tr>
          </thead>
          <tbody>
            {keys.map((key) => {
              const proposed = row.proposed_treatments[key] ?? "";
              const product =
                base.obligations.find((item) => item.obligation_key === key)?.product.code ??
                row.lines.map(record).find((line) => line.obligation_key === key)?.product_code;
              const edit = basis[key];
              const stored = basisOf(storedBasis[key]);
              const error = attempted ? (basisErrors[key] ?? null) : null;
              return (
                <tr key={key} className="border-b border-hairline align-top">
                  <th scope="row" className="px-2 py-2 text-start font-medium text-fg-1">
                    <span className="font-mono text-mono-sm">{key}</span>
                    {typeof product === "string" ? (
                      <>
                        {" "}
                        <span className="ms-1 text-fg-2">{product}</span>
                      </>
                    ) : null}
                  </th>
                  <td className="px-2 py-2">{treatmentLabel(proposed)}</td>
                  <td className="px-2 py-1">
                    <select
                      aria-label={t("modifications.wizard.treatment.chosenFor", { key })}
                      value={chosen[key] ?? proposed}
                      disabled={busy}
                      onChange={(event) =>
                        setChosen((current) => ({ ...current, [key]: event.target.value }))
                      }
                      className="h-[var(--control-h)] w-full min-w-64 rounded-md border border-control bg-surface px-2 text-body text-fg-1"
                    >
                      {offered.map((treatment) => (
                        <option key={treatment} value={treatment}>
                          {treatmentLabel(treatment)}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="px-2 py-2">
                    {stored.versionId !== null ? (
                      // The price test the row states for an added line, whatever the preparer
                      // answered (04 §16.14 rev 1.250 `price_tests`): none for a row that is not
                      // classified or was edited since, and for a line the engine does not test.
                      <SspBasisLabel
                        versionId={stored.versionId}
                        override={stored.override}
                        test={priceTestOf(row, key)}
                        currency={row.currency}
                      />
                    ) : (chosen[key] ?? proposed) === "CUMULATIVE_CATCH_UP" ? (
                      t("modifications.wizard.treatment.inceptionSsp")
                    ) : (
                      <NoValue />
                    )}
                  </td>
                  <td className="px-2 py-2">
                    {edit === undefined || versionOptions.length === 0 ? (
                      <NoValue />
                    ) : (
                      <div className="flex flex-col gap-2">
                        <label className="flex items-center gap-2 text-body-sm text-fg-1">
                          <input
                            type="checkbox"
                            className="size-4"
                            aria-label={t("modifications.wizard.treatment.useAnotherFor", { key })}
                            checked={edit.override}
                            disabled={busy}
                            onChange={(event) =>
                              setBasis((current) => ({
                                ...current,
                                [key]: { ...edit, override: event.target.checked },
                              }))
                            }
                          />
                          {t("modifications.wizard.treatment.useAnother")}
                        </label>
                        {edit.override ? (
                          <>
                            <select
                              aria-label={t("modifications.wizard.treatment.versionFor", { key })}
                              aria-invalid={error !== null && edit.versionId === null}
                              aria-describedby={error === null ? undefined : `${errorId}-${key}`}
                              value={edit.versionId ?? ""}
                              disabled={busy}
                              onChange={(event) =>
                                setBasis((current) => ({
                                  ...current,
                                  [key]: {
                                    ...edit,
                                    versionId:
                                      event.target.value === "" ? null : event.target.value,
                                  },
                                }))
                              }
                              className="h-[var(--control-h)] rounded-md border border-control bg-surface px-2 text-body text-fg-1"
                            >
                              <option value="">{t("common.form.select.placeholder")}</option>
                              {versionOptions.map((version) => (
                                <option key={version.id} value={version.id}>
                                  {version.label}
                                </option>
                              ))}
                            </select>
                            <input
                              type="text"
                              aria-label={t("modifications.wizard.treatment.justificationFor", {
                                key,
                              })}
                              placeholder={t("modifications.wizard.treatment.justification")}
                              aria-invalid={error !== null && edit.versionId !== null}
                              aria-describedby={error === null ? undefined : `${errorId}-${key}`}
                              value={edit.justification}
                              disabled={busy}
                              onChange={(event) =>
                                setBasis((current) => ({
                                  ...current,
                                  [key]: { ...edit, justification: event.target.value },
                                }))
                              }
                              className="h-[var(--control-h)] rounded-md border border-control bg-surface px-2 text-body text-fg-1 placeholder:text-fg-3"
                            />
                            {error === null ? null : (
                              <p id={`${errorId}-${key}`} className="text-caption text-negative-fg">
                                {error}
                              </p>
                            )}
                          </>
                        ) : null}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <WizardFooter
        blocked={blocked}
        back={{ label: t("modifications.wizard.back"), onBack }}
        next={
          <Button
            variant="primary"
            loading={busy}
            disabledReason={blocked ?? undefined}
            onClick={goOn}
          >
            {t("modifications.wizard.next")}
          </Button>
        }
      />
      {recording ? (
        <JudgementDrawer
          modificationId={row.id}
          topics={[OVERRIDE_TOPIC]}
          onClose={() => setRecording(false)}
          onRecorded={async (judgement) => {
            // The record is linked with the departure it explains, in one save.
            await onSave(body(judgement.id));
            setRecording(false);
          }}
        />
      ) : null}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------
// Step 4: Impact preview (SCREENS §7.7).

function PreviewStep({
  row,
  base,
  command,
  contextPeriod,
}: {
  readonly row: Modification;
  readonly base: WizardBase;
  /** `POST /modifications/{id}/preview`: its job is adopted and the row read again when it ends. */
  readonly command: CommandState<PreviewJob>;
  readonly contextPeriod: string | null;
}) {
  const [unreached, setUnreached] = useState(false);
  const { job, jobId, pending } = command;
  const state = job?.state ?? null;

  const run = async () => {
    setUnreached(false);
    const outcome = await command.submit({});
    setUnreached(outcome.kind === "network-error");
  };

  // The step runs the preview of a row that holds none, once per row version. A preview this
  // reader is not shown is one the row holds (SCREENS §7.7 rev 1.77): nothing is run for it.
  const held = holdsStoredPreview(row);
  const startedFor = useRef<number | null>(null);
  useEffect(() => {
    if (!held && jobId === null && !pending && startedFor.current !== row.row_version) {
      startedFor.current = row.row_version;
      void run();
    }
    // `run` sends the command of this render; the effect follows the row version.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [held, jobId, pending, row.row_version]);

  // The run stores the preview on the row, which the command reads again when the job has ended.
  useEffect(() => {
    if (state === "SUCCEEDED" || state === "SUCCEEDED_WITH_EXCEPTIONS") {
      announce(t("modifications.wizard.preview.calculated"), "polite");
    }
  }, [state]);

  const label = t("modifications.wizard.preview.calculating");
  const failure: Failure | null = unreached ? "unreached" : command.problem;
  const again = (
    <div>
      <Button variant="secondary" onClick={() => void run()}>
        {t("modifications.wizard.preview.run")}
      </Button>
    </div>
  );
  const failed =
    job !== undefined && job.state === "FAILED" ? (
      <Banner
        tone="negative"
        title={t("modifications.wizard.preview.failed")}
        announce="live"
        headingLevel={3}
        actions={
          <Button variant="link" onClick={() => void run()}>
            {t("modifications.wizard.preview.run")}
          </Button>
        }
      >
        {(job.problem?.errors ?? []).length === 0 ? (
          job.problem === null ? null : (
            <p>{job.problem.title}</p>
          )
        ) : (
          (job.problem?.errors ?? []).map((error) => <p key={error.message}>{error.message}</p>)
        )}
        <p>{t("common.job.reference", { reference: job.id.slice(0, 8) })}</p>
      </Banner>
    ) : null;
  return (
    <div className="flex flex-col gap-4">
      <ProblemNotice problem={failure} />
      {row.impact_preview !== null ? (
        <>
          {/* A run started over a stored preview (SCREENS §7.7 rev 1.52) that failed: the stored one stays. */}
          {failed}
          <ModificationImpact
            summary={row.impact_preview}
            currency={row.currency}
            contextPeriod={contextPeriod}
            periodLabel={base.periodLabel}
            added={addedKeys(row)}
            headingLevel={3}
            latestPostablePeriod={base.latestPostablePeriod}
            onRunPreview={() => void run()}
            previewRunning={pending || state === "QUEUED" || state === "RUNNING"}
          />
        </>
      ) : row.impact_preview_withheld ? (
        // The run of this step, where there was one, has ended: the notice is inserted after load.
        <PreviewWithheld row={row} announce={jobId === null ? "static" : "live"} />
      ) : failed !== null ? (
        failed
      ) : job !== undefined && (job.state === "QUEUED" || job.state === "RUNNING") ? (
        <JobProgress label={label} job={job} unit={t("modifications.wizard.preview.unit")} />
      ) : failure !== null ? (
        again
      ) : (
        <div className="flex flex-col gap-3">
          <p role="status" className="text-body-sm text-fg-2">
            {label}
          </p>
          <Skeleton region={label} shape="rows" count={4} />
          {job?.state === "CANCELLED" ? again : null}
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------------------------------
// Step 5: Submit (SCREENS §7.8).

/**
 * Why "Submit for approval" is held back, or null (SCREENS §7.8, rev 1.51 and rev 1.66): the record
 * of a departing treatment that waits for its review, or that explains nothing any more — rejected,
 * discarded; a judgement record of the modification that is a draft or waits for review, which is
 * reviewed, or discarded, first (PRD ERR-95; the first of them is named); a linked estimate version
 * that is not approved (PRD ERR-87). The API's refusal stays the backstop of each.
 */
function submitBlocked(
  row: Modification,
  departing: readonly string[],
  linked: Judgement | undefined,
  judgements: readonly Judgement[],
): string | null {
  if (departing.length > 0 && linked !== undefined) {
    const number = linked.judgement_no;
    if (linked.status === "SUBMITTED") {
      return t("modifications.wizard.submit.judgementWaiting", { number });
    }
    if (linked.status === "REJECTED") {
      return t("modifications.wizard.submit.judgementRejected", { number });
    }
    // A draft is the next rule's: it is discarded, or sent for review, like any record of the row.
    if (linked.status !== "REVIEWED" && linked.status !== "DRAFT") {
      return t("modifications.wizard.submit.judgementNotStanding", {
        number,
        status: judgementStatusLabel(linked.status),
      });
    }
  }
  const unreviewed = judgements.find(
    (item) => item.status === "DRAFT" || item.status === "SUBMITTED",
  );
  if (unreviewed !== undefined) {
    return t("modifications.wizard.submit.recordNotReviewed", {
      number: unreviewed.judgement_no,
    });
  }
  return unapprovedVersionLine(row);
}

export function SummaryList({
  row,
  judgements,
  departing,
}: {
  readonly row: Modification;
  readonly judgements: readonly Judgement[];
  readonly departing: readonly string[];
}) {
  const treatments = Object.keys(row.chosen_treatments).sort((left, right) =>
    left.localeCompare(right, undefined, { numeric: true }),
  );
  const items: readonly (readonly [string, ReactNode])[] = [
    [t("modifications.wizard.change.kind"), kindLabel(row.kind)],
    [t("modifications.wizard.change.reference"), row.reference ?? row.modification_no],
    [t("modifications.wizard.change.effectiveDate"), formatDate(row.effective_date)],
    [
      t("modifications.wizard.summary.treatments"),
      treatments.length === 0 ? (
        <NoValue />
      ) : (
        <ul className="flex flex-col gap-0.5">
          {treatments.map((key) => (
            <li key={key}>
              <span className="font-mono text-mono-sm">{key}</span>{" "}
              {treatmentLabel(row.chosen_treatments[key] ?? "")}
            </li>
          ))}
        </ul>
      ),
    ],
    [
      t("modifications.wizard.linked.versions"),
      <LinkedVersionsSummary versions={linkedVersionsOf(row)} />,
    ],
    [
      t("modifications.wizard.linked.judgements"),
      judgements.length === 0 ? (
        t("modifications.wizard.linked.none")
      ) : (
        <ul className="flex flex-col gap-0.5">
          {judgements.map((item) => (
            <li key={item.id}>
              <span className="font-mono text-mono-sm">{item.judgement_no}</span>{" "}
              {topicLabel(item.topic)} · {judgementStatusLabel(item.status)}
            </li>
          ))}
        </ul>
      ),
    ],
    [
      t("modifications.wizard.summary.flags"),
      departing.length === 0 ? (
        t("modifications.wizard.summary.noFlags")
      ) : (
        <OutlineChip label={t("modifications.wizard.override.chip")} />
      ),
    ],
  ];
  return (
    <dl
      data-testid="SF-07-summary"
      className="grid max-w-[var(--content-max-form)] grid-cols-[max-content_1fr] gap-x-6 gap-y-2"
    >
      {items.map(([label, value]) => (
        <div key={label} className="contents">
          <dt className="text-body-sm text-fg-3">{label}</dt>
          <dd className="text-body text-fg-1">{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function SubmitStep({
  row,
  judgements,
  departing,
  comment,
  onComment,
  problem,
  busy,
}: {
  readonly row: Modification;
  readonly judgements: readonly Judgement[];
  readonly departing: readonly string[];
  readonly comment: string;
  readonly onComment: (value: string) => void;
  readonly problem: Failure | null;
  readonly busy: boolean;
}) {
  return (
    <div className="flex flex-col gap-4" aria-busy={busy || undefined}>
      <ProblemNotice problem={problem} />
      <SummaryList row={row} judgements={judgements} departing={departing} />
      <TextField
        name="comment"
        label={t("modifications.wizard.submit.comment")}
        optional
        multiline
        value={comment}
        onChange={onComment}
      />
    </div>
  );
}
