// SF-12 bulk approval (SCREENS §15.5, §15.10; DESIGN_SYSTEM DS-CMP-10, DS-CMP-11, DS-CMP-20; 04 API-R-09
// `POST /approvals/bulk-approve`, §16.10; REQ-PLT-014, REQ-PLT-017, REQ-UX-013; PRD BR-PLT-06; BUILD_SPEC
// WEB-16). On Waiting for me, the bulk layout replaces the master list by a grid with a checkbox column:
// Request, Type, Currency, Amount, Preparer, Submitted, oldest first, with the view's filter chips. The
// selection bar reads "<n> selected" and "Approve <n> items"; the modal lists the items with the impact
// line of each, takes the comment and the statement that every item was reviewed, and sends each item
// with the hashes of its own row. The command answers one result per item: when every item was approved
// a toast says so; otherwise the result dialog "Approved <m> of <n> items" lists each refusal by request
// with the problem's title and detail. A 403 `mfa-step-up-required` opens the step-up dialog before any
// item is decided, and the command is sent again with the same key (SCR-PERM-05). Only loaded rows can
// be selected: the hashes are the row's, and the command takes at most 200 items.
import { type FormEvent, useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { DataGrid } from "../../components/data-grid/DataGrid";
import type { GridColumn, GridSelection, GridSource } from "../../components/data-grid/types";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { useToast } from "../../components/feedback/Toast";
import { reasonError, ReasonField } from "../../components/form/ReasonField";
import { WarningCircle, X } from "../../components/icons/registry";
import { Money } from "../../components/money/Money";
import { NoValue } from "../../components/money/Num";
import { Button } from "../../components/ui/Button";
import { trapTab, useModalFocus } from "../../components/ui/dialog";
import { Modal } from "../../components/ui/Modal";
import { useCommand } from "../../lib/api/commands";
import { fetchListPage, type ListPage } from "../../lib/api/lists";
import {
  BULK_APPROVE_PATH,
  BULK_LIMIT,
  type BulkApprove,
  type BulkApproved,
  type BulkApproveResult,
  bulkGridKey,
  bulkItem,
} from "../../lib/api/queries/approval-delegations";
import {
  type Approval,
  type ApprovalListFilters,
  APPROVALS_PATH,
  currencyRegistered,
  effectiveDateReached,
  ensureCurrencies,
  EVERY_APPROVAL,
  viewQuery,
} from "../../lib/api/queries/approvals";
import { placeProblem } from "../../lib/api/refusals";
import { formatMoney, formatNumber, timestampDate } from "../../lib/format";
import { t } from "../../lib/i18n/t";
import { StepUpModal } from "../settings/profile";

const STEP_UP_REQUIRED_SLUG = "mfa-step-up-required";
const PARTS_SEPARATOR = " · ";
const TABLE = "w-full border-separate border-spacing-0 rounded-md border border-default bg-surface";
const HEADER = "px-3 py-2 text-start text-body-sm font-medium text-fg-2";
const CELL = "border-t border-hairline px-3 py-2 text-body-sm text-fg-1";

/** One page of Waiting for me with the view's chips, for the bulk grid: every row carries its hashes. */
async function fetchWaitingPage(
  filters: ApprovalListFilters,
  cursor: string | null,
): Promise<ListPage<Approval>> {
  const page = await fetchListPage<Approval>(
    APPROVALS_PATH,
    viewQuery("waiting", filters),
    cursor,
    {
      limit: BULK_LIMIT,
      count: false,
    },
  );
  await ensureCurrencies(page.items);
  return page;
}

function amountCell(approval: Approval) {
  const amount = approval.amount;
  // A currency the viewer's reads did not register shows no amount (L3-3-Q-26).
  return amount === null || !currencyRegistered(amount.currency) ? (
    <NoValue />
  ) : (
    <Money value={amount.amount} currency={amount.currency} variant="cell" />
  );
}

function requestCell(approval: Approval) {
  return (
    <span className="flex min-w-0 items-baseline gap-2">
      <span className="shrink-0 font-mono text-mono-sm text-fg-2">{approval.request_no}</span>
      <span className="truncate" title={approval.summary}>
        {approval.summary}
      </span>
    </span>
  );
}

/**
 * SCREENS §15.5 columns: Request, Type, Currency, Amount, Preparer, Submitted. The widths and the
 * checkbox column take 1,144 px of the 1,158 px the grid has at 1440 px beside the open rail, which
 * leaves a scrollbar's width. Each column is as wide as its header needs beside the column menu
 * button ("Currency" at 88 px cut its own label), and Request takes what the others leave: the
 * summary tells one request from the next, so it is the last text to be cut.
 */
export function bulkColumns(): readonly GridColumn<Approval>[] {
  return [
    {
      id: "request",
      header: t("approvals.bulk.column.request"),
      kind: "identifier",
      value: (approval) => approval.summary,
      render: requestCell,
      width: 400,
    },
    {
      id: "type",
      header: t("approvals.bulk.column.type"),
      kind: "text",
      value: (approval) => t(`approvals.subjectType.${approval.subject.type}`),
      width: 200,
    },
    {
      id: "currency",
      header: t("approvals.bulk.column.currency"),
      kind: "text",
      value: (approval) => approval.amount?.currency ?? null,
      currencyColumn: true,
      width: 112,
    },
    {
      id: "amount",
      header: t("approvals.bulk.column.amount"),
      kind: "money",
      value: (approval) => approval.amount?.amount ?? null,
      render: amountCell,
      width: 120,
    },
    {
      id: "preparer",
      header: t("approvals.bulk.column.preparer"),
      kind: "user",
      value: (approval) => approval.preparer.display_name,
      // A name of some sixteen characters on one line ("Hannah Lindqvist").
      width: 160,
    },
    {
      id: "submitted",
      header: t("approvals.bulk.column.submitted"),
      kind: "date",
      value: (approval) => timestampDate(approval.submitted_at),
      width: 112,
    },
  ];
}

function listed(value: unknown): number {
  return Array.isArray(value) ? value.length : 0;
}

/** A summary member that states nothing: null, zero, an empty list or an empty object (§15.4 region 4). */
function statesNothing(value: unknown): boolean {
  if (value === null || value === undefined || value === 0 || value === "0") {
    return true;
  }
  if (Array.isArray(value)) {
    return value.length === 0;
  }
  return typeof value === "object" && Object.keys(value).length === 0;
}

/**
 * SCREENS §15.5 "Impact summary line": what the stored preview's summary states, without arithmetic —
 * the catch-up total when the preview names one, the number of periods whose revenue it lists and the
 * number of journal lines; "No impact on revenue or balances." for a request without figures (§15.4).
 */
export function impactLine(approval: Approval): string {
  const summary = approval.impact_preview?.summary;
  if (summary === undefined || Object.values(summary).every(statesNothing)) {
    return t("approvals.request.noImpact");
  }
  const parts: string[] = [];
  const catchUp = summary.catch_up_total;
  if (catchUp !== null && currencyRegistered(catchUp.currency)) {
    parts.push(
      t("approvals.bulk.impact.catchUp", {
        amount: formatMoney(catchUp.amount, catchUp.currency, { variant: "inline" }),
      }),
    );
  }
  const periods = listed(summary.revenue_by_period_after);
  if (periods > 0) {
    parts.push(
      t("approvals.bulk.impact.periods", {
        count: periods,
        formatted: formatNumber(periods, { kind: "count" }),
      }),
    );
  }
  const lines = listed(summary.journal_lines);
  if (lines > 0) {
    parts.push(
      t("approvals.bulk.impact.journalLines", {
        count: lines,
        formatted: formatNumber(lines, { kind: "count" }),
      }),
    );
  }
  return parts.length === 0 ? t("approvals.bulk.impact.preview") : parts.join(PARTS_SEPARATOR);
}

interface BulkApproveModalProps {
  readonly approvals: readonly Approval[];
  readonly onClose: () => void;
  readonly onDone: (results: readonly BulkApproveResult[]) => void;
}

// docs/dev-guide.md DG-FE-06: the one field of the modal and the member it sends. What a refusal says
// of an item of the selection is the banner's.
const BULK_MEMBERS = { comment: ["comment"] } as const;

/** SCREENS §15.5 modal "Approve <n> items". */
function BulkApproveModal({ approvals, onClose, onDone }: BulkApproveModalProps) {
  const formId = useId();
  const itemsId = useId();
  const reviewedId = useId();
  const reviewedErrorId = useId();
  const [comment, setComment] = useState("");
  const [reviewed, setReviewed] = useState(false);
  const [attempted, setAttempted] = useState(false);
  const [stepUp, setStepUp] = useState(false);
  const approve = useCommand<BulkApproved>({
    method: "POST",
    path: BULK_APPROVE_PATH,
    invalidates: [EVERY_APPROVAL],
  });
  const title = t("approvals.approveN", { count: approvals.length });

  const send = async () => {
    const outcome = await approve.submit({
      comment: comment.trim(),
      items: approvals.map(bulkItem),
    } satisfies BulkApprove);
    if (outcome.kind === "succeeded" && outcome.data !== null) {
      onDone(outcome.data.results);
      return;
    }
    if (outcome.kind === "failed" && outcome.problem.slug === STEP_UP_REQUIRED_SLUG) {
      setStepUp(true);
    }
  };
  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setAttempted(true);
    if (approve.pending || reasonError(comment) !== null || !reviewed) {
      return;
    }
    void send();
  };

  const problem = approve.problem;
  const placed = useMemo(() => placeProblem(problem, BULK_MEMBERS), [problem]);
  const reviewedMissing = attempted && !reviewed;
  return (
    <>
      <Modal
        open
        // DS-CMP-11: a form at `--modal-w-lg`, the width of the diff variant (SCREENS §15.5).
        variant="diff"
        title={title}
        primaryAction={{ label: title, form: formId }}
        submitting={approve.pending}
        onClose={onClose}
        testId="SF-12-dialog-bulk-approve"
      >
        <form id={formId} noValidate onSubmit={submit} className="flex flex-col gap-4 pb-1">
          {problem === null || problem.slug === STEP_UP_REQUIRED_SLUG ? null : (
            <RefusalBanner problem={problem} placed={placed} />
          )}
          <table aria-labelledby={itemsId} className={TABLE}>
            <caption id={itemsId} className="sr-only">
              {t("approvals.bulk.items")}
            </caption>
            <thead>
              <tr>
                <th scope="col" className={HEADER}>
                  {t("approvals.bulk.column.request")}
                </th>
                <th scope="col" className={HEADER}>
                  {t("approvals.bulk.column.type")}
                </th>
                <th scope="col" className={HEADER}>
                  {t("approvals.bulk.column.impact")}
                </th>
                <th scope="col" className={`${HEADER} text-end`}>
                  {t("approvals.bulk.column.amount")}
                </th>
              </tr>
            </thead>
            <tbody>
              {approvals.map((approval) => (
                <tr key={approval.id}>
                  <th scope="row" className={`${CELL} text-start font-normal`}>
                    <span className="flex flex-col">
                      <span className="font-mono text-mono-sm text-fg-2">
                        {approval.request_no}
                      </span>
                      <span>{approval.summary}</span>
                    </span>
                  </th>
                  <td className={CELL}>{t(`approvals.subjectType.${approval.subject.type}`)}</td>
                  <td className={CELL}>{impactLine(approval)}</td>
                  <td className={`${CELL} whitespace-nowrap text-end`}>
                    {approval.amount === null || !currencyRegistered(approval.amount.currency) ? (
                      <NoValue />
                    ) : (
                      <Money
                        value={approval.amount.amount}
                        currency={approval.amount.currency}
                        variant="inline"
                      />
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <ReasonField
            name="bulk_comment"
            label={t("approvals.comment.label")}
            value={comment}
            onChange={setComment}
            showError={attempted}
            error={placed.fields.comment}
          />
          <div className="flex flex-col gap-1">
            <label htmlFor={reviewedId} className="flex items-start gap-2 text-body-sm text-fg-1">
              <input
                id={reviewedId}
                type="checkbox"
                required
                checked={reviewed}
                aria-invalid={reviewedMissing ? true : undefined}
                aria-describedby={reviewedMissing ? reviewedErrorId : undefined}
                onChange={(event) => setReviewed(event.target.checked)}
                className="mt-0.5 size-4 shrink-0"
              />
              {t("approvals.bulk.reviewed")}
            </label>
            {reviewedMissing ? (
              <p
                id={reviewedErrorId}
                className="flex items-start gap-1 text-body-sm text-negative-fg"
              >
                <WarningCircle aria-hidden="true" className="mt-0.5 shrink-0" />
                {t("approvals.bulk.reviewedRequired")}
              </p>
            ) : null}
          </div>
        </form>
      </Modal>
      {stepUp ? (
        <StepUpModal
          onCancel={() => setStepUp(false)}
          onVerified={() => {
            setStepUp(false);
            void send();
          }}
        />
      ) : null}
    </>
  );
}

/** A request the command did not approve, with the problem of its own item. */
export interface BulkFailure {
  readonly approval: Approval;
  readonly title: string;
  readonly detail: string | null;
}

/** The refusals among `results`, in the order of the selection. */
export function bulkFailures(
  approvals: readonly Approval[],
  results: readonly BulkApproveResult[],
): readonly BulkFailure[] {
  const byId = new Map(results.map((result) => [result.approval_request_id, result]));
  return approvals.flatMap((approval) => {
    const problem = byId.get(approval.id)?.problem ?? null;
    if (problem === null) {
      return [];
    }
    if (effectiveDateReached(problem)) {
      // PRD ERR-75 asks the author for another date; the approver is told what she can do.
      return [
        {
          approval,
          title: t("approvals.problem.effectiveReachedTitle"),
          detail: t("approvals.problem.effectiveReached", {
            name: approval.preparer.display_name,
          }),
        },
      ];
    }
    const messages = (problem.errors ?? []).map((error) => error.message);
    // A problem whose detail is the message of one of its errors says it once.
    const detail = [...new Set([problem.detail ?? null, ...messages])].filter(
      (text): text is string => text !== null && text !== "",
    );
    return [
      { approval, title: problem.title, detail: detail.length === 0 ? null : detail.join(" ") },
    ];
  });
}

interface BulkResultDialogProps {
  readonly total: number;
  readonly failures: readonly BulkFailure[];
  readonly onClose: () => void;
}

/** SCREENS §15.5 result "Approved <m> of <n> items" with the failures table. */
function BulkResultDialog({ total, failures, onClose }: BulkResultDialogProps) {
  const titleId = useId();
  const tableId = useId();
  const panel = useRef<HTMLDivElement>(null);
  const title = useRef<HTMLHeadingElement>(null);
  useModalFocus({ panel, initialFocus: title });

  useEffect(() => {
    const root = panel.current;
    if (root === null) {
      return undefined;
    }
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        event.stopPropagation();
        onClose();
        return;
      }
      trapTab(event, root);
    };
    root.addEventListener("keydown", onKeyDown);
    return () => root.removeEventListener("keydown", onKeyDown);
  }, [onClose]);

  return createPortal(
    <div
      className="fixed inset-0 z-[var(--z-modal)] flex justify-center bg-scrim p-4"
      style={{ paddingBlockStart: "15vh" }}
    >
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
        data-testid="SF-12-dialog-bulk-result"
        className="flex max-h-full w-[var(--modal-w-lg)] max-w-full flex-col self-start rounded-xl border border-hairline bg-raised shadow-overlay"
      >
        <div className="flex items-start justify-between gap-2 px-5 pt-5">
          <h2 ref={title} id={titleId} tabIndex={-1} className="text-title-md text-fg-1">
            {t("approvals.bulk.result.title", {
              approved: formatNumber(total - failures.length, { kind: "count" }),
              count: total,
              formatted: formatNumber(total, { kind: "count" }),
            })}
          </h2>
          <Button
            variant="ghost"
            size="sm"
            icon={X}
            aria-label={t("common.dialog.close")}
            onClick={onClose}
          />
        </div>
        <div className="min-h-0 overflow-y-auto px-5 pt-4">
          <table aria-labelledby={tableId} className={TABLE}>
            <caption id={tableId} className="pb-2 text-start text-body-sm font-semibold text-fg-1">
              {t("approvals.bulk.result.failures")}
            </caption>
            <thead>
              <tr>
                <th scope="col" className={HEADER}>
                  {t("approvals.bulk.column.request")}
                </th>
                <th scope="col" className={HEADER}>
                  {t("approvals.bulk.result.problem")}
                </th>
                <th scope="col" className={HEADER}>
                  {t("approvals.bulk.result.detail")}
                </th>
              </tr>
            </thead>
            <tbody>
              {failures.map((failure) => (
                <tr key={failure.approval.id}>
                  <th scope="row" className={`${CELL} text-start font-normal`}>
                    <span className="flex flex-col">
                      <span className="font-mono text-mono-sm text-fg-2">
                        {failure.approval.request_no}
                      </span>
                      <span>{failure.approval.summary}</span>
                    </span>
                  </th>
                  <td className={CELL}>{failure.title}</td>
                  <td className={CELL}>{failure.detail ?? <NoValue />}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="flex justify-end px-5 py-4">
          <Button variant="primary" onClick={onClose}>
            {t("approvals.bulk.result.done")}
          </Button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

export interface BulkApprovalProps {
  /** The chips of Waiting for me (SCREENS §15.3). */
  readonly filters: ApprovalListFilters;
}

/** SCREENS §15.5: the selection grid of Waiting for me with its modal and its result. */
export function BulkApproval({ filters }: BulkApprovalProps) {
  const toast = useToast();
  // Rows by id as the pages arrive: the selection names ids, the command needs each row's hashes.
  const loaded = useRef(new Map<string, Approval>());
  const [selected, setSelected] = useState<readonly string[]>([]);
  const [confirming, setConfirming] = useState<readonly Approval[] | null>(null);
  const [result, setResult] = useState<{
    readonly total: number;
    readonly failures: readonly BulkFailure[];
  } | null>(null);
  // A new grid after a command: the selection of decided rows does not outlive them.
  const [generation, setGeneration] = useState(0);

  const columns = useMemo(() => bulkColumns(), []);
  const source: GridSource<Approval> = useMemo(
    () => ({
      queryKey: bulkGridKey(filters),
      fetchPage: async (cursor) => {
        const page = await fetchWaitingPage(filters, cursor);
        for (const approval of page.items) {
          loaded.current.set(approval.id, approval);
        }
        return page;
      },
    }),
    [filters],
  );
  const onSelectionChange = useCallback((selection: GridSelection) => {
    setSelected([...selection.ids]);
  }, []);

  const open = () => {
    const approvals = selected.flatMap((id) => {
      const approval = loaded.current.get(id);
      return approval === undefined ? [] : [approval];
    });
    if (approvals.length > 0) {
      setConfirming(approvals);
    }
  };
  const restart = () => {
    setSelected([]);
    setGeneration((value) => value + 1);
  };
  const done = (approvals: readonly Approval[], results: readonly BulkApproveResult[]) => {
    const failures = bulkFailures(approvals, results);
    setConfirming(null);
    if (failures.length === 0) {
      toast.show({
        tone: "positive",
        message: t("approvals.bulk.approved", {
          count: approvals.length,
          formatted: formatNumber(approvals.length, { kind: "count" }),
        }),
      });
      restart();
      return;
    }
    setResult({ total: approvals.length, failures });
  };

  const tooMany = selected.length > BULK_LIMIT;
  return (
    <div className="flex h-full min-h-0 flex-col">
      <DataGrid<Approval>
        key={generation}
        name="bulk"
        title={t("approvals.bulk.title")}
        errorTitle={t("approvals.list.loadError")}
        countLabel={(count) => t("approvals.list.count", { count })}
        columns={columns}
        source={source}
        rowKey={(approval) => approval.id}
        rowLabel={(approval) => approval.summary}
        selectable
        onSelectionChange={onSelectionChange}
        bulkActions={(selection) => (
          <Button
            variant="primary"
            size="sm"
            disabledReason={
              tooMany
                ? t("approvals.bulk.tooMany", {
                    count: BULK_LIMIT,
                    formatted: formatNumber(BULK_LIMIT, { kind: "count" }),
                  })
                : undefined
            }
            onClick={open}
          >
            {t("approvals.approveN", { count: selection.ids.size })}
          </Button>
        )}
        testIdPrefix="SF-12"
        rowTestKey={(approval) => approval.request_no}
        emptyState={
          <EmptyState
            title={t("approvals.empty.waiting.title")}
            description={t("approvals.empty.waiting.description")}
          />
        }
        noResults={<EmptyState title={t("approvals.noResults")} description="" />}
      />
      {confirming === null ? null : (
        <BulkApproveModal
          approvals={confirming}
          onClose={() => setConfirming(null)}
          onDone={(results) => done(confirming, results)}
        />
      )}
      {result === null ? null : (
        <BulkResultDialog
          total={result.total}
          failures={result.failures}
          onClose={() => {
            setResult(null);
            restart();
          }}
        />
      )}
    </div>
  );
}
