// SF-12:request (SCREENS §15.1, §15.4, §15.6, §15.10; §0.6 SCR-PERM-02, SCR-PERM-05; §0.7; DESIGN_SYSTEM
// DS-CMP-11, DS-CMP-16, DS-CMP-29; 04 API-R-09 §16.10; PRD SM-01, BR-PLT-06, ERR-02 to ERR-04, ERR-28;
// REQ-UX-012, REQ-PLT-013). RT-57 renders inside the view that contains the request: Waiting for me when
// `can_decide`, Submitted by me for the preparer, otherwise All requests; `?view=` overrides. The pane
// holds the request header with the routing steps, the segregation-of-duties notice, the impact notice,
// the generic field diff of the stored preview, the attachments and, when the viewer can decide, the
// decision form. Approve sends the reviewed hashes, re-sends with the same Idempotency-Key after the
// step-up modal, toasts "Approved: <summary>." and opens the next request. Reject confirms first.
// `self-approval` and `approver-already-decided` show their ERR copy inside the form; `stale-approval`
// turns the chip to Stale and removes the form. The preparer can withdraw a pending request.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, type RefObject, useEffect, useId, useRef, useState } from "react";
import { Link, matchPath, useNavigate, useParams, useSearchParams } from "react-router";

import { MFA_ENROL_PATH } from "../../app/auth/MfaGate";
import { fetchSession } from "../../app/auth/RequireSession";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { controlClass, Field, fieldId } from "../../components/form/Field";
import { ReasonField, reasonError } from "../../components/form/ReasonField";
import { Switch } from "../../components/form/Switch";
import { CaretDown } from "../../components/icons/registry";
import { Button } from "../../components/ui/Button";
import { cn } from "../../components/ui/cn";
import { Modal } from "../../components/ui/Modal";
import { chipFor, StatusChip, type StatusWord } from "../../components/ui/StatusChip";
import { isTypingTarget } from "../../lib/a11y/typing";
import type { CommandOutcome } from "../../lib/api/commands";
import { ApiProblem } from "../../lib/api/problems";
import {
  type Approval,
  type ApprovalAction,
  type ApprovalApproveIn,
  type ApprovalSubjectType,
  type ApprovalView,
  currencyRegistered,
  effectiveDateReached,
  EVERY_APPROVAL,
  FILE_CONTENT_PATH,
  isApprovalView,
  isMoney,
  isRecord,
  type PreviewDocument,
  useApproval,
  useApprovalCommand,
  usePreviewDocument,
} from "../../lib/api/queries/approvals";
import {
  contractJudgementsKey,
  fetchContractJudgements,
  type Judgement,
} from "../../lib/api/queries/contracts";
import { judgementStatusLabel } from "../../lib/api/queries/judgements";
import { fetchPeriods, type Period, periodLabel, periodsKey } from "../../lib/api/queries/tenant";
import type { components } from "../../lib/api/schema";
import { queryKeys } from "../../lib/api/query-keys";
import { formatDate, formatMoney, formatTimestamp, MINUS_SIGN, NO_VALUE } from "../../lib/format";
import { hasMessage, t } from "../../lib/i18n/t";
import { useBuiltPaths } from "../settings/index";
import { StepUpModal } from "../settings/profile";
import {
  ApprovalsPage,
  approvalChipWord,
  entitiesLabel,
  problemMessage,
  subjectTypeLabel,
} from "./inbox";

type ImpactPreview = components["schemas"]["ImpactPreviewOut"];

/** SCREENS §15.1: the view that contains a request when the URL names none. */
export function containingView(approval: Approval, viewerId: string | null): ApprovalView {
  if (approval.can_decide) {
    return "waiting";
  }
  return viewerId !== null && approval.preparer.id === viewerId ? "submitted" : "all";
}

/**
 * SCREENS §15.4 region 1 (rev 1.18): the routes whose record the link "Open <subject label>" names.
 * Any other route of the client reads "Open record".
 */
export const SUBJECT_ROUTES = [
  { path: "/contracts/:contractId", label: "approvals.subjectLink.contract" },
  { path: "/journals/runs/:runId", label: "approvals.subjectLink.journalRun" },
  { path: "/settings/products/:productId", label: "approvals.subjectLink.product" },
  { path: "/policies/accounting/:policyId", label: "approvals.subjectLink.accountingPolicy" },
  { path: "/data/exceptions/:exceptionId", label: "approvals.subjectLink.exception" },
  { path: "/settings/support-access", label: "approvals.subjectLink.supportAccess" },
] as const;

export interface SubjectLink {
  /** The address the link opens: the path of `subject.href` with its search and hash. */
  readonly to: string;
  readonly label: string;
}

/**
 * The link of `subject.href`, or null when the request names no subject route or names one the
 * client does not hold (`built`, the route patterns of the router).
 */
export function subjectLink(href: string | null, built: ReadonlySet<string>): SubjectLink | null {
  if (href === null || !href.startsWith("/") || href.startsWith("//")) {
    return null;
  }
  const pathname = href.split(/[?#]/)[0] ?? "";
  const holds = (path: string) =>
    built.has(path) && matchPath({ path, end: true }, pathname) !== null;
  const named = SUBJECT_ROUTES.find((route) => holds(route.path));
  if (named !== undefined) {
    return { to: href, label: t(named.label) };
  }
  const other = [...built].some((path) => path !== "*" && holds(path));
  return other ? { to: href, label: t("approvals.subjectLink.record") } : null;
}

function isEmptyFigure(value: unknown): boolean {
  if (value === null || value === undefined || value === 0 || value === "0") {
    return true;
  }
  if (Array.isArray(value)) {
    return value.length === 0;
  }
  return typeof value === "object" && Object.keys(value).length === 0;
}

/** SCREENS §15.4 region 4: true when the preview carries no revenue, balance or journal figure. */
export function impactIsEmpty(preview: ImpactPreview | null): boolean {
  return preview === null || Object.values(preview.summary).every(isEmptyFigure);
}

export type ChangeKind = "added" | "removed" | "changed" | "unchanged";

export interface FieldChange {
  readonly id: string;
  readonly field: string;
  readonly kind: ChangeKind;
  readonly current: string | null;
  readonly proposed: string | null;
  /** What the row's values cover, shown under the field name (SCREENS §15.4 region 5, rev 1.18). */
  readonly note?: string;
}

/**
 * Members the generic diff never shows: surrogate identifiers (`id`, `*_id`), identifier lists (`*_ids`)
 * and the proposal's object type. External ids are business keys and stay visible.
 */
const HIDDEN_MEMBER = /^(?!(?:.*_)?external_id$)(?:(?:.*_)?ids?|object_type)$/;

/** D-90a QA-L9-5a: a record shows its members to this depth; a deeper record shows no value. */
const RECORD_DEPTH = 2;
const MEMBER_SEPARATOR = " · ";

/** "role_code" reads "Role code"; a member with an `approvals.diff.member.*` key reads that copy. */
export function memberLabel(name: string): string {
  const key = `approvals.diff.member.${name}`;
  if (hasMessage(key)) {
    return t(key);
  }
  const words = name.replaceAll("_", " ").trim();
  return `${words.charAt(0).toUpperCase()}${words.slice(1)}`;
}

/** Names the periods of a preview: the tenant calendar label, else the raw key (D-90a QA-L9-5a). */
export type PeriodLabeller = (periodKey: string) => string;

const RAW_PERIOD_KEY: PeriodLabeller = (periodKey) => periodKey;

/**
 * DS-FMT-19 labels from API-S-Period rows through `periodLabel`. A key without a row, a row whose label
 * cannot be formatted and a key whose rows disagree read as the raw key; nothing throws.
 */
export function periodLabeller(
  rows: readonly Pick<Period, "period">[] | undefined,
): PeriodLabeller {
  const labels = new Map<string, string | null>();
  for (const row of rows ?? []) {
    const key = row.period.period_key;
    let label: string | null;
    try {
      label = periodLabel(row.period);
    } catch {
      label = null;
    }
    labels.set(key, labels.has(key) && labels.get(key) !== label ? null : label);
  }
  return (periodKey) => labels.get(periodKey) ?? periodKey;
}

function hasExactly(value: Readonly<Record<string, unknown>>, names: readonly string[]): boolean {
  return (
    Object.keys(value).length === names.length && names.every((name) => Object.hasOwn(value, name))
  );
}

/** A period amount `{period_key, amount}` (API-S-ImpactSummary rows, API-S-Import deltas). */
function isPeriodAmount(
  value: Readonly<Record<string, unknown>>,
): value is { readonly period_key: string; readonly amount: unknown } {
  return hasExactly(value, ["period_key", "amount"]) && typeof value.period_key === "string";
}

/** API-S-Ref `{id, code, name}`, shown by its code. */
function isRef(value: Readonly<Record<string, unknown>>): value is { readonly code: string } {
  return hasExactly(value, ["id", "code", "name"]) && typeof value.code === "string";
}

/** Whether a preview member holds a period amount at any depth. */
export function holdsPeriodAmounts(value: unknown): boolean {
  if (Array.isArray(value)) {
    const items: readonly unknown[] = value;
    return items.some((item) => holdsPeriodAmounts(item));
  }
  return (
    isRecord(value) &&
    (isPeriodAmount(value) || Object.values(value).some((item) => holdsPeriodAmounts(item)))
  );
}

export interface DisplayOptions {
  readonly periodLabel?: PeriodLabeller;
  /** The request's subject type: it names the enumeration of a preview's `status` (rev 1.18). */
  readonly subjectType?: ApprovalSubjectType;
}

/** SCREENS §0.8: the enumeration of the member `status` in the preview of a subject type. */
const STATUS_ENUM: Partial<Record<ApprovalSubjectType, string>> = {
  CONTRACT_ACTIVATION: "E-17",
  CONTRACT_VOID: "E-17",
};

/** The status word the product shows for a literal; a literal without a word reads as sent. */
function statusWord(enumId: string, literal: string): string {
  try {
    return chipFor(enumId, literal)?.status ?? literal;
  } catch {
    return literal;
  }
}

/** The first period of a `revenue_by_period` member, or null when it lists none. */
function firstPeriodKey(value: unknown): string | null {
  const first: unknown = Array.isArray(value) ? value[0] : null;
  return isRecord(first) && isPeriodAmount(first) ? first.period_key : null;
}

/**
 * A preview member as text (DS-CMP-16; D-90a QA-L9-5a): null for no value; Yes or No for booleans;
 * API-S-Money through the format module (DS-FMT-01, DS-FMT-05), or no value while its currency is not
 * registered (L3-3-Q-26); a period amount as "<period label> <amount>"; an API-S-Ref as its code; a
 * record as "<label> <value>" joined with " · " to depth 2, and an empty record as no value; lists of
 * values joined with commas, lists of records one per line, nested lists of records with semicolons.
 */
export function displayValue(value: unknown, options: DisplayOptions = {}): string | null {
  return formatMember(value, 1, options.periodLabel ?? RAW_PERIOD_KEY);
}

function formatMember(value: unknown, depth: number, label: PeriodLabeller): string | null {
  if (value === null || value === undefined) {
    return null;
  }
  if (typeof value === "boolean") {
    return t(value ? "approvals.diff.yes" : "approvals.diff.no");
  }
  if (typeof value === "string" || typeof value === "number") {
    return String(value);
  }
  if (Array.isArray(value)) {
    const items: readonly unknown[] = value;
    if (items.length === 0) {
      return null;
    }
    let separator = ", ";
    if (items.some((item) => isRecord(item) && !isMoney(item))) {
      separator = depth === 1 ? "\n" : "; ";
    }
    return items.map((item) => formatMember(item, depth, label) ?? NO_VALUE).join(separator);
  }
  if (!isRecord(value)) {
    return null;
  }
  if (isMoney(value)) {
    return currencyRegistered(value.currency)
      ? formatMoney(value.amount, value.currency, { variant: "inline" })
      : null;
  }
  if (isRef(value)) {
    return value.code;
  }
  if (isPeriodAmount(value)) {
    return `${label(value.period_key)} ${formatMember(value.amount, depth + 1, label) ?? NO_VALUE}`;
  }
  if (depth > RECORD_DEPTH) {
    return null;
  }
  const pairs = Object.entries(value)
    .filter(([name]) => !HIDDEN_MEMBER.test(name))
    .map(([name, member]) => `${memberLabel(name)} ${memberText(name, member, depth, label)}`);
  return pairs.length === 0 ? null : pairs.join(MEMBER_SEPARATOR);
}

/** A record member one level down; an account role reads its catalogue label (`accountRole.*`). */
function memberText(name: string, member: unknown, depth: number, label: PeriodLabeller): string {
  if (
    name === "account_role" &&
    typeof member === "string" &&
    hasMessage(`accountRole.${member}`)
  ) {
    return t(`accountRole.${member}`);
  }
  return formatMember(member, depth + 1, label) ?? NO_VALUE;
}

/** The generic field diff (DS-CMP-16): each member of `after` against `before`. */
export function fieldChanges(
  document: PreviewDocument,
  options: DisplayOptions = {},
): FieldChange[] {
  const names = [...new Set([...Object.keys(document.before), ...Object.keys(document.after)])];
  return names
    .filter((name) => !HIDDEN_MEMBER.test(name))
    .map((name) => {
      const inBefore = Object.hasOwn(document.before, name);
      const inAfter = Object.hasOwn(document.after, name);
      const statusEnum =
        name === "status" && options.subjectType !== undefined
          ? STATUS_ENUM[options.subjectType]
          : undefined;
      const text = (value: unknown): string | null =>
        statusEnum !== undefined && typeof value === "string"
          ? statusWord(statusEnum, value)
          : displayValue(value, options);
      const current = inBefore ? text(document.before[name]) : null;
      const proposed = inAfter ? text(document.after[name]) : null;
      let kind: ChangeKind = "changed";
      if (!inBefore) {
        kind = "added";
      } else if (!inAfter) {
        kind = "removed";
      } else if (JSON.stringify(document.before[name]) === JSON.stringify(document.after[name])) {
        kind = "unchanged";
      }
      const change: FieldChange = { id: name, field: memberLabel(name), kind, current, proposed };
      // 04 API-S-ImpactSummary: `revenue_by_period` holds six periods from the effective period.
      const first =
        name === "revenue_by_period"
          ? (firstPeriodKey(document.after[name]) ?? firstPeriodKey(document.before[name]))
          : null;
      return first === null
        ? change
        : {
            ...change,
            note: t("approvals.diff.note.revenueByPeriod", {
              period: (options.periodLabel ?? RAW_PERIOD_KEY)(first),
            }),
          };
    });
}

export function ApprovalRequest() {
  const { requestId = "" } = useParams();
  const [search] = useSearchParams();
  const session = useQuery({ queryKey: queryKeys.session(), queryFn: fetchSession }).data;
  const viewerId = session?.authenticated === true ? session.user.id : null;
  const approval = useApproval(requestId);
  const override = search.get("view");

  // The derived view is kept per request, so a decision that changes `can_decide` keeps the list.
  const [pinned, setPinned] = useState<{ readonly id: string; readonly view: ApprovalView } | null>(
    null,
  );
  let derived: ApprovalView | null = null;
  if (approval.data !== undefined) {
    derived = containingView(approval.data, viewerId);
  } else if (approval.isError) {
    derived = "all";
  }
  useEffect(() => {
    if (derived !== null && pinned?.id !== requestId) {
      setPinned({ id: requestId, view: derived });
    }
  }, [derived, pinned, requestId]);

  let view: ApprovalView | null = derived;
  if (isApprovalView(override)) {
    view = override;
  } else if (pinned?.id === requestId) {
    view = pinned.view;
  }

  if (view === null) {
    return (
      <div className="flex flex-col gap-3">
        <h1 tabIndex={-1} className="text-title-lg text-fg-1">
          {t("approvals.title")}
        </h1>
        <Skeleton region={t("approvals.request.regionPending")} shape="rows" count={6} />
      </div>
    );
  }

  return (
    <ApprovalsPage
      view={view}
      selectedId={requestId}
      detailLabel={
        approval.data === undefined
          ? t("approvals.request.regionPending")
          : t("approvals.request.region", { summary: approval.data.summary })
      }
      renderDetail={({ moveToNext }) => (
        <RequestDetail requestId={requestId} viewerId={viewerId} onApproved={moveToNext} />
      )}
    />
  );
}

interface RequestDetailProps {
  readonly requestId: string;
  readonly viewerId: string | null;
  readonly onApproved: () => void;
}

function RequestDetail({ requestId, viewerId, onApproved }: RequestDetailProps) {
  const approval = useApproval(requestId);
  if (approval.data === undefined) {
    if (approval.isError) {
      const notFound = approval.error instanceof ApiProblem && approval.error.status === 404;
      return (
        <div className="p-[var(--panel-pad)]">
          {notFound ? (
            <EmptyState
              title={t("approvals.request.notFound")}
              description={t("errors.notFound.description")}
            />
          ) : (
            <Banner
              tone="negative"
              title={t("approvals.request.loadError")}
              headingLevel={2}
              actions={
                <Button variant="link" onClick={() => void approval.refetch()}>
                  {t("approvals.retry")}
                </Button>
              }
            >
              {problemMessage(approval.error)}
            </Banner>
          )}
        </div>
      );
    }
    return (
      <div className="flex flex-col gap-4 p-[var(--panel-pad)]">
        <Skeleton region={t("approvals.request.regionPending")} shape="text" count={3} />
        <Skeleton region={t("approvals.request.regionPending")} shape="rows" count={4} />
      </div>
    );
  }
  return (
    <RequestReview
      key={approval.data.id}
      approval={approval.data}
      viewerId={viewerId}
      onApproved={onApproved}
    />
  );
}

interface RequestReviewProps {
  readonly approval: Approval;
  readonly viewerId: string | null;
  readonly onApproved: () => void;
}

function RequestReview({ approval, viewerId, onApproved }: RequestReviewProps) {
  const attachmentsId = useId();
  const justificationId = useId();
  const link = subjectLink(approval.subject.href, useBuiltPaths());
  const [staleAfterDecision, setStaleAfterDecision] = useState(false);
  // 03 REQ-PLT-015: a request is approved on the preview the approver read. The stored preview is
  // the same query GenericFieldDiff renders; while it has not loaded, or cannot be loaded (the file
  // does not answer, or holds no preview document), Approve is unavailable here, as the API refuses
  // it (04 API-R-09).
  // SCREENS §15.4 "Content withheld" (rev 1.32, restated in rev 1.48; 04 API-S-Approval
  // `content_withheld`): the request names legal entities the reader does not cover, so the pane
  // shows who asked, what kind of request it is and how far it has come, and one banner in place of
  // its content. A decision's comment is rendered whenever the API sends one, here as for any
  // request: the API decides who reads which comment, and the pane knows nothing of that rule.
  const withheld = approval.content_withheld;
  const previewFileId = withheld ? null : (approval.impact_preview?.file_id ?? null);
  const preview = usePreviewDocument(previewFileId);
  const previewRead = previewFileId === null || (preview.data ?? null) !== null;
  const previewUnreadable = !previewRead && !preview.isPending;
  const stale =
    staleAfterDecision ||
    (approval.status === "VOIDED" && approval.void_reason === "STALE_SUBJECT");
  const chip: StatusWord = stale ? "Stale" : approvalChipWord(approval);
  const pending = approval.status === "PENDING" && !stale;
  const entities = entitiesLabel(approval);
  const viewerIsPreparer = viewerId !== null && approval.preparer.id === viewerId;
  const earlierApprover =
    viewerId !== null &&
    approval.steps.some((step) =>
      step.decisions.some((decision) => decision.approver.id === viewerId),
    );

  let sod: string | null = null;
  if (pending && !approval.can_decide) {
    if (viewerIsPreparer) {
      sod = t("approvals.sod.preparer");
    } else if (earlierApprover) {
      sod = t("approvals.sod.earlierApprover");
    } else if (!withheld) {
      // The banner of a withheld request says why nothing is decided here: the reader may well
      // hold the right and lack an entity (SCREENS §15.4 region 2, rev 1.48).
      sod = t("approvals.sod.noRights");
    }
  }

  return (
    <article className="flex min-h-full flex-col gap-4 px-[var(--panel-pad)] pt-[var(--panel-pad)]">
      <header className="flex flex-col gap-2">
        <div className="flex flex-wrap items-center gap-2">
          <h2 className="flex flex-wrap items-baseline gap-2 text-title-md text-fg-1">
            <span data-volatile="" className="font-mono text-mono-sm text-fg-2">
              {approval.request_no}
            </span>
            <span>{subjectTypeLabel(approval.subject.type)}</span>
          </h2>
          <StatusChip status={chip} />
        </div>
        <p className="text-body text-fg-1">{approval.summary}</p>
        <p className="text-body-sm text-fg-2">
          {t("approvals.request.submittedBy", {
            name: approval.preparer.display_name,
            at: formatTimestamp(approval.submitted_at),
          })}
        </p>
        {entities === null ? null : (
          <p className="text-body-sm text-fg-2" data-testid="SF-12-entities">
            {t("approvals.request.entities", { entities })}
          </p>
        )}
        <ol
          aria-label={t("approvals.request.routing")}
          className="flex flex-col gap-1.5 text-body-sm"
        >
          {approval.steps.map((step) => (
            <li key={step.step_no} className="flex flex-col gap-0.5">
              <span className="text-fg-1">
                {t("approvals.request.step", {
                  name: step.name,
                  recorded: step.decisions.length,
                  required: step.min_approvers,
                })}
              </span>
              {step.decisions.map((decision) => (
                <span key={decision.id} className="flex flex-wrap gap-x-2 text-fg-2">
                  <span>{decision.approver.display_name}</span>
                  {decision.on_behalf_of === null ? null : (
                    <span>
                      {t("approvals.request.onBehalfOf", {
                        name: decision.on_behalf_of.display_name,
                      })}
                    </span>
                  )}
                  <span>{formatTimestamp(decision.decided_at)}</span>
                  {decision.comment === null ? null : <q>{decision.comment}</q>}
                </span>
              ))}
            </li>
          ))}
        </ol>
        {link === null ? null : (
          <p>
            <Link
              to={link.to}
              data-testid="SF-12-subject-link"
              className="text-body-sm text-accent-fg hover:text-accent-fg-hover hover:underline"
            >
              {link.label}
            </Link>
          </p>
        )}
      </header>
      {sod === null ? null : (
        <div data-testid="SF-12-banner-sod">
          <Banner tone="info" title={sod} announce="static" headingLevel={3} />
        </div>
      )}
      {stale ? (
        <Banner
          tone="warning"
          title={t("approvals.stale.title")}
          announce={staleAfterDecision ? "live" : "static"}
          headingLevel={3}
        >
          {t("approvals.stale.message")}
        </Banner>
      ) : null}
      {approval.comment === null || approval.comment.trim() === "" ? null : (
        // SCREENS §15.4 region 3 (04 API-S-Approval `comment`, rev 1.252): the comment the request was
        // submitted with. It is rendered whenever the API sends it, for a withheld request too — the
        // API answers it to the preparer alone there — and the pane holds no rule about who reads it.
        // A comment that is blank after trimming says nothing and is treated as none: the API's
        // bodies admit one (the supervisor's ruling of 2026-10-02 06:30).
        <section
          aria-labelledby={justificationId}
          data-testid="SF-12-justification"
          className="flex flex-col gap-1"
        >
          <h3 id={justificationId} className="text-body-sm font-semibold text-fg-1">
            {t("approvals.request.justification")}
          </h3>
          <blockquote className="whitespace-pre-wrap border-s-2 border-default ps-3 text-body-sm text-fg-1">
            {approval.comment}
          </blockquote>
        </section>
      )}
      {withheld ? (
        <div data-testid="SF-12-banner-content-withheld">
          <Banner
            tone="info"
            title={t("approvals.withheld.title")}
            announce="static"
            headingLevel={3}
          >
            {t("approvals.withheld.message")}
          </Banner>
        </div>
      ) : (
        <>
          {approval.reopen_judgement == null ? null : (
            <section className="flex flex-col gap-2" aria-label={t("close.reopen.evidenceLabel")}>
              <h3 className="text-title-sm text-fg-1">{approval.reopen_judgement.judgement_no}</h3>
              <p className="whitespace-pre-wrap text-body-sm text-fg-1">
                {approval.reopen_judgement.conclusion}
              </p>
              <p className="whitespace-pre-wrap text-body-sm text-fg-2">
                {approval.reopen_judgement.rationale}
              </p>
              <p className="text-body-sm text-fg-2">
                {t("close.reopen.evidenceReviewer", {
                  name: approval.reopen_judgement.reviewer.display_name,
                })}
              </p>
              {approval.reopen_judgement.contract_id === null ? null : (
                <Link
                  className="text-accent-fg hover:underline"
                  to={`/contracts/${approval.reopen_judgement.contract_id}`}
                >
                  {t("close.reopen.evidenceContract")}
                </Link>
              )}
            </section>
          )}
          <CriteriaMetRegion approval={approval} />
          {approval.impact_preview === null ? (
            // SCREENS §15.4 region 4 (rev 1.18): nothing was computed, so the pane claims no impact and
            // says what the approver can do instead.
            <div data-testid="SF-12-banner-no-preview">
              <Banner
                tone="info"
                title={t("approvals.noPreview.title")}
                announce="static"
                headingLevel={3}
              >
                {noPreviewMessage(link !== null, pending && approval.can_decide, approval)}
              </Banner>
            </div>
          ) : impactIsEmpty(approval.impact_preview) ? (
            <p className="text-body-sm text-fg-2">{t("approvals.request.noImpact")}</p>
          ) : null}
          {previewUnreadable ? (
            <div data-testid="SF-12-banner-preview">
              <Banner
                tone="warning"
                title={t("approvals.preview.unreadable.title")}
                announce="static"
                headingLevel={3}
                actions={
                  <Button variant="link" onClick={() => void preview.refetch()}>
                    {t("approvals.retry")}
                  </Button>
                }
              >
                {t("approvals.preview.unreadable.message")}
              </Banner>
            </div>
          ) : null}
          <GenericFieldDiff
            fileId={previewFileId}
            entity={approval.entity?.code ?? null}
            subjectType={approval.subject.type}
          />
          {approval.attachments.length === 0 ? null : (
            <section aria-labelledby={attachmentsId} className="flex flex-col gap-1">
              <h3 id={attachmentsId} className="text-body-sm font-semibold text-fg-1">
                {t("approvals.request.attachments")}
              </h3>
              <ul className="flex flex-col gap-1">
                {approval.attachments.map((attachment, index) => (
                  <li key={attachment.file_id}>
                    <a
                      href={`${FILE_CONTENT_PATH}/${attachment.file_id}/content`}
                      className="text-body-sm text-accent-fg hover:text-accent-fg-hover hover:underline"
                    >
                      {attachment.original_filename ??
                        t("approvals.request.attachmentUnnamed", { number: index + 1 })}
                    </a>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}
      <div className="flex-1" />
      {pending && approval.can_decide ? (
        <DecisionForm
          approval={approval}
          previewRead={previewRead}
          onApproved={onApproved}
          onStale={() => setStaleAfterDecision(true)}
        />
      ) : null}
      {pending && viewerIsPreparer ? <WithdrawAction approval={approval} /> : null}
    </article>
  );
}

/**
 * SCREENS §15.4 region 4 (rev 1.18): what a request without a stored preview tells its reader. The
 * viewer who can decide is told what to do before deciding; any other reader what the pane lacks.
 */
function noPreviewMessage(linked: boolean, decides: boolean, approval: Approval): string {
  if (linked) {
    return t(decides ? "approvals.noPreview.withLink.decide" : "approvals.noPreview.withLink.read");
  }
  return decides
    ? t("approvals.noPreview.noLink.decide", { name: approval.preparer.display_name })
    : t("approvals.noPreview.noLink.read");
}

/** The reviewed Step 1 record a book's criteria-met assessment cites, as one line. */
function recordLine(record: Judgement | undefined, pending: boolean): string {
  if (record === undefined) {
    return pending ? t("approvals.criteriaMet.record.loading") : NO_VALUE;
  }
  if (record.status === "REVIEWED" && record.reviewer !== null && record.reviewed_at !== null) {
    return t("approvals.criteriaMet.record.reviewed", {
      number: record.judgement_no,
      name: record.reviewer.display_name,
      at: formatTimestamp(record.reviewed_at),
    });
  }
  // Any other status, in the words the contract workbench uses for its Step 1 record.
  return t("contracts.workbench.step1.record", {
    number: record.judgement_no,
    status: judgementStatusLabel(record.status),
  });
}

/**
 * SCREENS §15.4 region 4 (rev 1.11; supervisor ruling R-61 (f); PRD SM-02 `NOT_A_CONTRACT` to
 * `PENDING_REVIEW`): the activation of a contract whose criteria were not met names what its approval
 * does — per book that moves, the date its criteria are met, the reviewed Step 1 record and the
 * catch-up of that book (04 §16.10 `impact_preview.summary.criteria_met`). The books are parallel
 * ledgers, so no figure adds them; the summary's `catch_up_total` is the primary book's and is one of
 * the rows. The records are read from `GET /judgements` by the contract; every other request renders
 * nothing.
 */
function CriteriaMetRegion({ approval }: { readonly approval: Approval }) {
  const headingId = useId();
  const books = approval.impact_preview?.summary.criteria_met ?? null;
  const moves = books !== null && books.length > 0;
  const records = useQuery({
    queryKey: contractJudgementsKey(approval.subject.id),
    queryFn: () => fetchContractJudgements(approval.subject.id),
    enabled: moves,
    retry: false,
  });
  if (books === null || !moves) {
    return null;
  }
  const bookLabel = (code: string) =>
    hasMessage(`shell.context.books.${code}`) ? t(`shell.context.books.${code}`) : code;
  return (
    <section
      aria-labelledby={headingId}
      data-testid="SF-12-criteria-met"
      className="flex flex-col gap-2"
    >
      <h3 id={headingId} className="text-body-sm font-semibold text-fg-1">
        {t("approvals.criteriaMet.title")}
      </h3>
      <p className="text-body-sm text-fg-2">{t("approvals.criteriaMet.message")}</p>
      <table
        aria-label={t("approvals.criteriaMet.caption")}
        className="w-full border-collapse text-body-sm"
      >
        <thead>
          <tr className="border-b border-default text-caption text-fg-3">
            {(["book", "date", "record", "catchUp"] as const).map((column) => (
              <th
                key={column}
                scope="col"
                className={cn(
                  "px-2 py-1.5 font-medium",
                  column === "catchUp" ? "text-end" : "text-start",
                )}
              >
                {t(`approvals.criteriaMet.column.${column}`)}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {books.map((item) => (
            <tr key={item.book} className="border-b border-hairline align-top">
              <th scope="row" className="px-2 py-1.5 text-start font-medium text-fg-1">
                {bookLabel(item.book)}
              </th>
              <td className="num px-2 py-1.5">{formatDate(item.effective_date)}</td>
              <td className="px-2 py-1.5">
                {recordLine(
                  records.data?.find((record) => record.id === item.judgement_record_id),
                  records.isPending,
                )}
              </td>
              <td className="num px-2 py-1.5 text-end">
                {displayValue(item.catch_up_total) ?? NO_VALUE}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

const MARKER: Readonly<Record<Exclude<ChangeKind, "unchanged">, string>> = {
  removed: MINUS_SIGN,
  added: "+",
  changed: "~",
};

interface GenericFieldDiffProps {
  readonly fileId: string | null;
  /** The request's entity code, which scopes the calendar read; null reads every entity's periods. */
  readonly entity: string | null;
  readonly subjectType: ApprovalSubjectType;
}

function GenericFieldDiff({ fileId, entity, subjectType }: GenericFieldDiffProps) {
  const preview = usePreviewDocument(fileId);
  const document = preview.data ?? null;
  // D-90a QA-L9-5a: period amounts read the tenant calendar label (DS-FMT-19). Without a calendar row
  // (no `config.read`, a failed read or an unknown key) the raw key stands.
  const calendarQuery: Readonly<Record<string, string>> = entity === null ? {} : { entity };
  const calendar = useQuery({
    queryKey: periodsKey(calendarQuery),
    queryFn: () => fetchPeriods(calendarQuery),
    enabled:
      document !== null &&
      (holdsPeriodAmounts(document.before) || holdsPeriodAmounts(document.after)),
    retry: false,
  });
  if (fileId === null) {
    return null;
  }
  if (preview.isPending || calendar.isLoading) {
    return <Skeleton region={t("common.diff.column.field")} shape="rows" count={3} />;
  }
  const changes =
    document === null
      ? []
      : fieldChanges(document, { periodLabel: periodLabeller(calendar.data), subjectType });
  // Lists of records read one per line.
  return changes.length === 0 ? null : (
    <div className="whitespace-pre-line">
      <FieldDiffTable changes={changes} />
    </div>
  );
}

function FieldDiffTable({ changes }: { readonly changes: readonly FieldChange[] }) {
  const root = useRef<HTMLDivElement>(null);
  const [showUnchanged, setShowUnchanged] = useState(false);
  const changed = changes.filter((change) => change.kind !== "unchanged");
  const shown = showUnchanged ? changes : changed;

  // N and Shift+N move between changed rows while focus is not in a field and no modal is open.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      const element = root.current;
      if (
        element === null ||
        (event.key !== "n" && event.key !== "N") ||
        event.altKey ||
        event.ctrlKey ||
        event.metaKey ||
        event.defaultPrevented ||
        isTypingTarget(event.target) ||
        document.querySelector("[aria-modal='true']") !== null
      ) {
        return;
      }
      const rows = Array.from(element.querySelectorAll<HTMLElement>("tr[data-change-row]"));
      if (rows.length === 0) {
        return;
      }
      event.preventDefault();
      const index = rows.findIndex((row) => row.contains(document.activeElement));
      let next: number;
      if (event.shiftKey) {
        next = index === -1 ? rows.length - 1 : Math.max(index - 1, 0);
      } else {
        next = Math.min(index + 1, rows.length - 1);
      }
      rows[next]?.focus();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  return (
    <div ref={root} data-testid="SF-12-diff" className="flex flex-col gap-2">
      {changed.length < changes.length ? (
        <Switch
          label={t("common.diff.showUnchanged")}
          checked={showUnchanged}
          onChange={setShowUnchanged}
        />
      ) : null}
      <table className="w-full border-collapse text-body-sm">
        <caption className="pb-2 text-start text-body-sm font-semibold text-fg-1">
          {t("common.diff.caption", { count: changed.length })}
        </caption>
        <thead>
          <tr className="border-b border-default text-caption text-fg-3">
            <th scope="col" className="w-16 px-2 py-1.5 text-start font-medium">
              {t("common.diff.column.change")}
            </th>
            <th scope="col" className="px-2 py-1.5 text-start font-medium">
              {t("common.diff.column.field")}
            </th>
            <th scope="col" className="px-2 py-1.5 text-start font-medium">
              {t("common.diff.column.current")}
            </th>
            <th scope="col" className="px-2 py-1.5 text-start font-medium">
              {t("common.diff.column.proposed")}
            </th>
          </tr>
        </thead>
        <tbody>
          {shown.map((change) => (
            <tr
              key={change.id}
              data-change={change.kind}
              data-change-row={change.kind === "unchanged" ? undefined : ""}
              tabIndex={change.kind === "unchanged" ? undefined : -1}
              className={cn(
                "focus-inset border-b border-hairline align-top",
                change.kind === "removed" && "bg-diff-removed-bg",
                change.kind === "added" && "bg-diff-added-bg",
              )}
            >
              <td className="px-2 py-1.5">
                {change.kind === "unchanged" ? null : (
                  <>
                    <span aria-hidden="true" className="num font-medium text-fg-1">
                      {MARKER[change.kind]}
                    </span>
                    <span className="sr-only">{t(`common.diff.prefix.${change.kind}`)}</span>
                  </>
                )}
              </td>
              <FieldHeader change={change} />
              <td className={cn("px-2 py-1.5", change.kind === "changed" && "bg-diff-removed-bg")}>
                <span
                  className={cn(
                    (change.kind === "removed" || change.kind === "changed") &&
                      "text-fg-2 line-through",
                  )}
                >
                  {change.current ?? NO_VALUE}
                </span>
              </td>
              <td className={cn("px-2 py-1.5", change.kind === "changed" && "bg-diff-added-bg")}>
                {change.proposed ?? NO_VALUE}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Content of the pane ends this close to the footer's box before it counts as lying beneath. */
const BELOW_TOLERANCE_PX = 1;
/** Marks the row the cue adds to a sticky footer (`MoreBelow`). */
const CUE_ROW = "data-cue-row";

/** What the cue's row adds to a footer's height: a small control and the footer's row gap. */
function cueRowHeight(footer: HTMLElement): string {
  const gap = getComputedStyle(footer).rowGap;
  return `var(--control-h-sm) + ${/^[\d.]+px$/.test(gap) ? gap : "0px"}`;
}

/**
 * SCREENS §15.4 region 7 (rev 1.18): a sticky footer covers the lower part of a request pane that is
 * taller than its viewport. While content lies beneath it the footer says so, and the pane's scroll
 * padding is the footer's height, so a change row that takes focus is never under it (DS-A11Y-03).
 * The pane is the DS-CMP-08 detail region around the request, the element that scrolls it.
 */
function usePaneBelow(footer: RefObject<HTMLElement | null>): {
  readonly below: boolean;
  readonly showMore: () => void;
} {
  const [below, setBelow] = useState(false);
  const measure = useRef<() => void>(() => undefined);
  const paneOf = (element: HTMLElement | null) =>
    element?.closest<HTMLElement>('[role="region"]') ?? null;
  useEffect(() => {
    const element = footer.current;
    const pane = paneOf(element);
    if (element === null || pane === null) {
      return undefined;
    }
    const read = () => {
      setBelow(pane.scrollHeight - pane.clientHeight - pane.scrollTop > BELOW_TOLERANCE_PX);
      // The footer is taller by the cue's row while the cue is shown, and the padding is that taller
      // height in both states: a row that takes focus while the cue is not shown would otherwise stop
      // flush with the shorter footer and be covered the moment the cue appears (found by the e2e row
      // in the whole gate: row 1 ended 29.5 px under the form).
      const height = `${String(element.offsetHeight)}px`;
      pane.style.scrollPaddingBlockEnd =
        element.querySelector(`[${CUE_ROW}]`) === null
          ? `calc(${height} + ${cueRowHeight(element)})`
          : height;
    };
    measure.current = read;
    read();
    pane.addEventListener("scroll", read, { passive: true });
    // The pane's own box and the footer's change with the viewport and with a refusal.
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(read);
    observer?.observe(pane);
    observer?.observe(element);
    // The preview arrives after the first paint. The request is a flex item that keeps the pane's
    // height while its content overflows it, so no observed box changes when the content grows: the
    // pane is measured again whenever its content does.
    const content = typeof MutationObserver === "undefined" ? null : new MutationObserver(read);
    content?.observe(pane, { childList: true, subtree: true, characterData: true });
    return () => {
      pane.removeEventListener("scroll", read);
      observer?.disconnect();
      content?.disconnect();
      pane.style.scrollPaddingBlockEnd = "";
      measure.current = () => undefined;
    };
  }, [footer]);
  const showMore = () => {
    const element = footer.current;
    const pane = paneOf(element);
    if (element === null || pane === null) {
      return;
    }
    // One view of the pane, less what the footer covers.
    pane.scrollTop += Math.max(pane.clientHeight - element.offsetHeight, 0);
    measure.current();
  };
  return { below, showMore };
}

/**
 * "More below", the first row of a sticky footer while content lies beneath it (`usePaneBelow`). It
 * sits inside the footer, at its upper edge, so that the cue itself covers nothing of the request.
 */
function MoreBelow({ onShow }: { readonly onShow: () => void }): ReactNode {
  return (
    <div {...{ [CUE_ROW]: "" }} className="flex justify-center">
      <Button
        variant="link"
        size="sm"
        icon={CaretDown}
        data-testid="SF-12-more-below"
        onClick={onShow}
      >
        {t("approvals.moreBelow")}
      </Button>
    </div>
  );
}

/** The field name of a change row; a note on what the row covers is its description. */
function FieldHeader({ change }: { readonly change: FieldChange }) {
  const noteId = useId();
  if (change.note === undefined) {
    return (
      <th scope="row" className="px-2 py-1.5 text-start font-medium text-fg-1">
        {change.field}
      </th>
    );
  }
  return (
    <th
      scope="row"
      aria-label={change.field}
      aria-describedby={noteId}
      className="px-2 py-1.5 text-start font-medium text-fg-1"
    >
      {change.field}
      <span id={noteId} className="mt-0.5 block text-caption font-normal text-fg-3">
        {change.note}
      </span>
    </th>
  );
}

const COMMENT_FIELD = "approvalComment";

interface DecisionFormProps {
  readonly approval: Approval;
  /** False while the request's stored impact preview has not been read (REQ-PLT-015). */
  readonly previewRead: boolean;
  readonly onApproved: () => void;
  readonly onStale: () => void;
}

function DecisionForm({ approval, previewRead, onApproved, onStale }: DecisionFormProps) {
  const navigate = useNavigate();
  const toast = useToast();
  const queryClient = useQueryClient();
  const approve = useApprovalCommand(approval.id, "approve");
  const reject = useApprovalCommand(approval.id, "reject");
  const [comment, setComment] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [stepUp, setStepUp] = useState<ApprovalAction | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const footer = useRef<HTMLFormElement>(null);
  const pane = usePaneBelow(footer);

  const commentIsValid = (): boolean => {
    setAttempted(true);
    if (reasonError(comment) !== null) {
      document.getElementById(fieldId(COMMENT_FIELD))?.focus();
      return false;
    }
    return true;
  };

  const settle = (action: ApprovalAction, outcome: CommandOutcome<Approval>) => {
    if (outcome.kind === "succeeded" || outcome.kind === "accepted") {
      setStepUp(null);
      setConfirming(false);
      const key = action === "approve" ? "approvals.toast.approved" : "approvals.toast.rejected";
      toast.show({ tone: "positive", message: t(key, { summary: approval.summary }) });
      if (action === "approve") {
        onApproved();
      }
      return;
    }
    if (outcome.kind === "network-error") {
      setStepUp(null);
      setConfirming(false);
      setProblem(t("approvals.problem.network"));
      return;
    }
    const failure = outcome.problem;
    if (failure.slug === "mfa-step-up-required") {
      setConfirming(false);
      setStepUp(action);
      return;
    }
    setStepUp(null);
    setConfirming(false);
    switch (failure.slug) {
      case "mfa-required":
        void navigate(MFA_ENROL_PATH);
        return;
      case "forbidden":
        toast.show({ tone: "negative", message: t("approvals.problem.forbidden") });
        return;
      case "self-approval":
        setProblem(t("approvals.problem.selfApproval"));
        return;
      case "approver-already-decided":
        setProblem(t("approvals.problem.alreadyDecided"));
        return;
      case "stale-approval":
        onStale();
        void queryClient.invalidateQueries({ queryKey: EVERY_APPROVAL });
        return;
      default:
        // PRD ERR-75 asks the author for another date; the approver is told what she can do.
        setProblem(
          effectiveDateReached(failure)
            ? t("approvals.problem.effectiveReached", { name: approval.preparer.display_name })
            : (failure.detail ?? failure.title),
        );
    }
  };

  const sendApprove = async () => {
    setProblem(null);
    const body: ApprovalApproveIn =
      approval.impact_preview === null
        ? { subject_content_sha256: approval.subject.content_sha256, comment: comment.trim() }
        : {
            subject_content_sha256: approval.subject.content_sha256,
            impact_preview_sha256: approval.impact_preview.sha256,
            comment: comment.trim(),
          };
    settle("approve", await approve.submit(body));
  };

  const sendReject = async () => {
    setProblem(null);
    settle("reject", await reject.submit({ comment: comment.trim() }));
  };

  return (
    <form
      ref={footer}
      aria-label={t("approvals.decision.label")}
      data-testid="SF-12-decision-form"
      noValidate
      onSubmit={(event) => event.preventDefault()}
      className="sticky bottom-0 flex flex-col gap-3 border-t border-hairline bg-surface py-3"
    >
      {pane.below ? <MoreBelow onShow={pane.showMore} /> : null}
      {problem === null ? null : <Banner tone="negative" title={problem} headingLevel={3} />}
      <ReasonField
        name={COMMENT_FIELD}
        label={t("approvals.comment.label")}
        value={comment}
        onChange={setComment}
        showError={attempted}
      />
      <div className="flex justify-end gap-2">
        <Button
          variant="secondary"
          onClick={() => {
            if (commentIsValid()) {
              setConfirming(true);
            }
          }}
        >
          {t("approvals.reject")}
        </Button>
        <Button
          variant="primary"
          loading={approve.pending}
          disabledReason={previewRead ? undefined : t("approvals.approve.needsPreview")}
          onClick={() => {
            if (commentIsValid()) {
              void sendApprove();
            }
          }}
        >
          {t("approvals.approve")}
        </Button>
      </div>
      <Modal
        open={confirming}
        variant="confirmation"
        title={t("approvals.reject.confirm.title", { summary: approval.summary })}
        description={t("approvals.reject.confirm.description")}
        primaryAction={{
          label: t("approvals.reject.confirm.action"),
          destructive: true,
          onAction: () => {
            void sendReject();
          },
        }}
        submitting={reject.pending}
        onClose={() => setConfirming(false)}
      >
        <div className="flex flex-col gap-1">
          <p className="text-caption text-fg-3">{t("approvals.reject.confirm.comment")}</p>
          <blockquote className="whitespace-pre-wrap border-s-2 border-default ps-3 text-body-sm text-fg-1">
            {comment.trim()}
          </blockquote>
        </div>
      </Modal>
      {stepUp === null ? null : (
        <StepUpModal
          onCancel={() => setStepUp(null)}
          onVerified={() => {
            const action = stepUp;
            setStepUp(null);
            void (action === "approve" ? sendApprove() : sendReject());
          }}
        />
      )}
    </form>
  );
}

function WithdrawAction({ approval }: { readonly approval: Approval }) {
  const toast = useToast();
  const withdraw = useApprovalCommand(approval.id, "withdraw");
  const [open, setOpen] = useState(false);
  const [comment, setComment] = useState("");
  const [problem, setProblem] = useState<string | null>(null);
  const commentField = "withdrawComment";
  const footer = useRef<HTMLDivElement>(null);
  const pane = usePaneBelow(footer);

  const send = async () => {
    setProblem(null);
    const text = comment.trim();
    const outcome = await withdraw.submit({ comment: text === "" ? null : text });
    setOpen(false);
    if (outcome.kind === "succeeded" || outcome.kind === "accepted") {
      toast.show({
        tone: "positive",
        message: t("approvals.toast.withdrawn", { summary: approval.summary }),
      });
      return;
    }
    setProblem(
      outcome.kind === "failed"
        ? (outcome.problem.detail ?? outcome.problem.title)
        : t("approvals.problem.network"),
    );
  };

  return (
    <div
      ref={footer}
      className="sticky bottom-0 flex flex-col gap-3 border-t border-hairline bg-surface py-3"
    >
      {pane.below ? <MoreBelow onShow={pane.showMore} /> : null}
      {problem === null ? null : <Banner tone="negative" title={problem} headingLevel={3} />}
      <div className="flex justify-end">
        <Button variant="secondary" onClick={() => setOpen(true)}>
          {t("approvals.withdraw")}
        </Button>
      </div>
      <Modal
        open={open}
        variant="confirmation"
        title={t("approvals.withdraw.confirm.title")}
        description={t("approvals.withdraw.confirm.description")}
        primaryAction={{
          label: t("approvals.withdraw"),
          onAction: () => {
            void send();
          },
        }}
        submitting={withdraw.pending}
        onClose={() => setOpen(false)}
      >
        <Field name={commentField} label={t("approvals.withdraw.comment")} optional>
          {(control) => (
            <textarea
              {...control}
              value={comment}
              rows={3}
              onChange={(event) => setComment(event.target.value)}
              className={cn(controlClass(false, true), "max-h-50 min-h-20 resize-none")}
            />
          )}
        </Field>
      </Modal>
    </div>
  );
}
