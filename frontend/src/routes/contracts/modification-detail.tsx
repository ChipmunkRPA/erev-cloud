// SF-07:detail Modification (SCREENS §7.8 to §7.10, §7.13; §0.4 RT-21; §0.7 SCR-ST-07; DESIGN_SYSTEM
// DS-CMP-16, DS-CMP-18; 04 API-R-31, §16.14 API-S-Modification, API-R-07 `GET /approvals/{id}`; PRD
// SM-03, BR-PLT-05, NTF-04; BUILD_SPEC CTR-27). A DRAFT renders the wizard for a holder of
// `modification.create`; any other status renders the read-only detail: "Change", "Answers",
// "Treatments", "Impact preview as submitted", "Approval" and, once applied, "Applied".
//
// A submitted modification shows its stepper with every step complete and its approval routing; the
// preparer may withdraw the request (a comment is required, as `/withdraw` takes one) or edit the
// modification, which voids the pending request and returns the row to Draft (BR-PLT-05). The preview
// shown is the row's own stored snapshot, the one `/submit` handed to the request.
//
// A rejected modification says so in a banner under the header, with its request and, for a holder
// of `modification.create` for the contract's entity, "Revise" (PRD SM-03 REJECTED → DRAFT; 04 §16.14
// rev 1.236, item MOD-REJECTED-REVISE-1; SCREENS §7.9 rev 1.65): the same empty `PATCH` as "Edit",
// after a confirmation of its own, since the rejected request was decided and stays closed. A draft
// rendered here, for a reader without `modification.create`, says of its earlier request what the
// wizard says (`DraftRequestNotice`).
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useId, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router";

import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { ReasonField, reasonError } from "../../components/form/ReasonField";
import { Money } from "../../components/money/Money";
import { NoValue, Num } from "../../components/money/Num";
import { type Step, Stepper } from "../../components/record/Stepper";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { chipFor, OutlineChip, StatusChip, statusMessageKey } from "../../components/ui/StatusChip";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { ApiProblem } from "../../lib/api/problems";
import {
  type Approval,
  approvalKey,
  type ApprovalStep,
  fetchApproval,
  requestRoute,
} from "../../lib/api/queries/approvals";
import type { Judgement } from "../../lib/api/queries/contracts";
import { useMe } from "../../lib/api/queries/me";
import {
  fetchModification,
  fetchModificationJudgements,
  holdsStoredPreview,
  type Modification,
  MODIFICATION_CREATE_PERMISSION,
  MODIFICATION_LIST_KEYS,
  MODIFICATION_RECORD_KEYS,
  modificationJudgementsKey,
  modificationKey,
  modificationPath,
  type ModificationUpdateBody,
  type ModificationWithdrawBody,
  QUESTIONS,
} from "../../lib/api/queries/modifications";
import { fetchSspVersionLabel, sspVersionLabelKey } from "../../lib/api/queries/obligations";
import {
  addedKeys,
  departures,
  type PriceTest,
  priceTestOf,
  WIZARD_STEPS,
} from "../../lib/forms/modification";
import { formatDate, formatTimestamp, parseDateInput } from "../../lib/format";
import { hasMessage, t } from "../../lib/i18n/t";
import { usePageStays } from "../../lib/url/live-search";
import { withParams } from "../../lib/url/params";
import { useBuiltPaths } from "../settings/index";
import { REQUEST_ROUTE } from "./obligation-pane";
import { ModificationImpact } from "./modification-impact";
import { LinkedVersionsTable, linkedVersionsOf } from "./modification-linked";
import {
  DraftRequestNotice,
  DraftWizard,
  type Failure,
  isTestedVersion,
  JudgementTable,
  LoadError,
  ModificationFrame,
  PreviewWithheld,
  priceRange,
  PriceTestLine,
  ProblemNotice,
  treatmentLabel,
  useWizardBase,
  type WizardBase,
} from "./modification-wizard";
import { contextSearch } from "./workbench";

const CONTRACT_READ = "contract.read";
/** SCREENS RT-33 SF-08:report, the target of the modification register link once it is built. */
const REPORT_ROUTE = "/reports/:reportCode";
const MODIFICATION_REGISTER = "modification_register";

function record(value: unknown): Readonly<Record<string, unknown>> {
  return typeof value === "object" && value !== null
    ? (value as Readonly<Record<string, unknown>>)
    : {};
}

function text(value: unknown): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

function flagLabel(flag: string): string {
  const key = `approvals.flag.${flag}`;
  return hasMessage(key) ? t(key) : flag;
}

/** The label of a T-PLT-11 approval permission, as the approvals screens name it. */
function permissionLabel(permission: string): string {
  const key = `approvals.permission.${permission}`;
  return hasMessage(key) ? t(key) : permission;
}

function Section({
  title,
  testId,
  children,
}: {
  readonly title: string;
  readonly testId?: string;
  readonly children: ReactNode;
}) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} data-testid={testId} className="flex flex-col gap-3">
      <h2 id={headingId} className="border-b border-hairline pb-2 text-title-sm text-fg-1">
        {title}
      </h2>
      {children}
    </section>
  );
}

const CELL = "px-2 py-1.5";
const HEAD = "px-2 py-1.5 font-medium";

function ChangeSection({ row }: { readonly row: Modification }) {
  const lines = row.lines.map(record);
  return (
    <Section title={t("modifications.wizard.steps.change")} testId="SF-07-section-change">
      <dl className="grid max-w-[var(--content-max-form)] grid-cols-[max-content_1fr] gap-x-6 gap-y-2">
        <dt className="text-body-sm text-fg-3">{t("modifications.wizard.change.kind")}</dt>
        <dd className="text-body text-fg-1">{t(`modification.kind.${row.kind}`)}</dd>
        <dt className="text-body-sm text-fg-3">{t("modifications.wizard.change.effectiveDate")}</dt>
        <dd className="text-body text-fg-1">{formatDate(row.effective_date)}</dd>
        <dt className="text-body-sm text-fg-3">{t("modifications.wizard.change.rationale")}</dt>
        <dd className="text-body text-fg-1">{row.rationale ?? <NoValue />}</dd>
        <dt className="text-body-sm text-fg-3">{t("contracts.modifications.column.preparedBy")}</dt>
        <dd className="text-body text-fg-1">{row.preparer.display_name}</dd>
      </dl>
      <div className="overflow-x-auto">
        <table data-testid="SF-07-grid-lines" className="w-full border-collapse text-body-sm">
          <caption className="pb-2 text-start text-title-sm text-fg-1">
            {t("modifications.wizard.change.lines.title")}
          </caption>
          <thead>
            <tr className="border-b border-default text-caption text-fg-3">
              {(["action", "obligationKey", "product"] as const).map((column) => (
                <th key={column} scope="col" className={`${HEAD} text-start`}>
                  {t(`modifications.wizard.change.column.${column}`)}
                </th>
              ))}
              <th scope="col" className={`${HEAD} text-end`}>
                {t("modifications.wizard.change.column.quantityChange")}
              </th>
              <th scope="col" className={`${HEAD} text-end`}>
                {t("modifications.wizard.change.column.considerationChangeIn", {
                  currency: row.currency,
                })}
              </th>
              {(["startDate", "endDate"] as const).map((column) => (
                <th key={column} scope="col" className={`${HEAD} text-start`}>
                  {t(`modifications.wizard.change.column.${column}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {lines.map((line, index) => {
              const action = text(line.action);
              const key = text(line.obligation_key) ?? "";
              const consideration = text(record(line.consideration_delta).amount);
              return (
                <tr key={`${key}:${String(index)}`} className="border-b border-hairline">
                  <td className={CELL}>
                    {action !== null && hasMessage(`modifications.wizard.change.action.${action}`)
                      ? t(`modifications.wizard.change.action.${action}`)
                      : (action ?? <NoValue />)}
                  </td>
                  <th scope="row" className={`${CELL} text-start font-mono text-mono-sm text-fg-1`}>
                    {key}
                  </th>
                  <td className={CELL}>{text(line.product_code) ?? <NoValue />}</td>
                  <td className={`${CELL} text-end`}>
                    <Num value={text(line.quantity_delta)} kind="quantity" />
                  </td>
                  <td className={`${CELL} text-end`}>
                    <Money value={consideration} currency={row.currency} delta />
                  </td>
                  <td className={CELL}>{lineDate(line.start_date) ?? <NoValue />}</td>
                  <td className={CELL}>{lineDate(line.end_date) ?? <NoValue />}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </Section>
  );
}

/** A date of the stored T-CON-06 line JSON as DS-FMT-16 text; null when the member holds none. */
function lineDate(value: unknown): string | null {
  if (typeof value !== "string" || value === "") {
    return null;
  }
  const parsed = parseDateInput(value);
  return parsed.ok ? formatDate(parsed.value) : value;
}

function AnswersSection({ row }: { readonly row: Modification }) {
  const stored = record(row.questionnaire);
  const keys = Object.keys(stored)
    .filter((key) =>
      QUESTIONS.some((question) => typeof record(stored[key])[question] === "boolean"),
    )
    .sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
  return (
    <Section title={t("modifications.detail.answers")} testId="SF-07-section-answers">
      {keys.length === 0 ? (
        <p className="text-body-sm text-fg-2">{t("modifications.detail.noAnswers")}</p>
      ) : (
        <div className="flex max-w-[var(--content-max-form)] flex-col gap-4">
          {keys.map((key) => (
            <div key={key} className="flex flex-col gap-1">
              <h3 className="font-mono text-mono text-fg-1">{key}</h3>
              <dl className="grid grid-cols-[1fr_max-content] gap-x-6 gap-y-1">
                {QUESTIONS.flatMap((question) => {
                  const value = record(stored[key])[question];
                  return typeof value === "boolean"
                    ? [
                        <div key={question} className="contents">
                          <dt className="text-body-sm text-fg-2">
                            {t(`modifications.question.${question}.label`)}
                          </dt>
                          <dd className="text-body text-fg-1">
                            {t(value ? "contracts.drawer.yes" : "contracts.drawer.no")}
                          </dd>
                          {question === "priced_at_ssp" ? (
                            // SCREENS §7.9 (rev 1.52): the engine's price test of the added line
                            // beside the answer, as the reviewer reads it (04 §16.14 rev 1.250
                            // `price_tests`): a second description of the question, on its own row
                            // and set in from the questions, which it would otherwise read as.
                            <PriceTestLine
                              row={row}
                              obligationKey={key}
                              as="dd"
                              className="col-span-2 ps-4 text-body-sm text-fg-2"
                            />
                          ) : null}
                        </div>,
                      ]
                    : [];
                })}
              </dl>
            </div>
          ))}
        </div>
      )}
    </Section>
  );
}

/**
 * The label of the stored SSP basis and, beside it, the range or the point of the price test the
 * row states for the line — while the basis is the version that test read, as on step 3 of the
 * wizard (SCREENS §7.6, §7.9).
 */
function BasisLabel({
  versionId,
  override,
  test,
  currency,
}: {
  readonly versionId: string;
  readonly override: boolean;
  readonly test: PriceTest | null;
  readonly currency: string;
}) {
  const label = useQuery({
    queryKey: sspVersionLabelKey(versionId),
    queryFn: () => fetchSspVersionLabel(versionId, null),
  });
  if (label.data === undefined || label.data.label === "") {
    return <NoValue />;
  }
  const range =
    test !== null && isTestedVersion(label.data, override, test)
      ? priceRange(test, currency)
      : null;
  return <>{range === null ? label.data.label : `${label.data.label} · ${range}`}</>;
}

function TreatmentsSection({ row }: { readonly row: Modification }) {
  const keys = [
    ...new Set([...Object.keys(row.proposed_treatments), ...Object.keys(row.chosen_treatments)]),
  ].sort((left, right) => left.localeCompare(right, undefined, { numeric: true }));
  const basis = record(row.ssp_basis);
  return (
    <Section title={t("modifications.detail.treatments")} testId="SF-07-section-treatments">
      {keys.length === 0 ? (
        <p className="text-body-sm text-fg-2">{t("modifications.detail.noTreatments")}</p>
      ) : (
        <table data-testid="SF-07-grid-treatments" className="w-full border-collapse text-body-sm">
          <caption className="sr-only">{t("modifications.wizard.treatment.caption")}</caption>
          <thead>
            <tr className="border-b border-default text-caption text-fg-3">
              {(["obligation", "proposed", "chosen", "sspBasis"] as const).map((column) => (
                <th key={column} scope="col" className={`${HEAD} text-start`}>
                  {t(`modifications.wizard.treatment.column.${column}`)}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {keys.map((key) => {
              const proposed = row.proposed_treatments[key];
              const chosen = row.chosen_treatments[key];
              const entry = record(basis[key]);
              const versionId = text(entry.ssp_book_version_id);
              return (
                <tr key={key} className="border-b border-hairline align-top">
                  <th scope="row" className={`${CELL} text-start font-mono text-mono-sm text-fg-1`}>
                    {key}
                  </th>
                  <td className={CELL}>
                    {proposed === undefined ? <NoValue /> : treatmentLabel(proposed)}
                  </td>
                  <td className={CELL}>
                    {chosen === undefined ? <NoValue /> : treatmentLabel(chosen)}
                  </td>
                  <td className={CELL}>
                    {versionId !== null ? (
                      <span className="flex flex-wrap items-center gap-2">
                        <BasisLabel
                          versionId={versionId}
                          override={entry.is_override === true}
                          test={priceTestOf(row, key)}
                          currency={row.currency}
                        />
                        {entry.is_override === true ? (
                          <OutlineChip label={t("modifications.detail.sspOverride")} />
                        ) : null}
                      </span>
                    ) : chosen === "CUMULATIVE_CATCH_UP" ? (
                      t("modifications.wizard.treatment.inceptionSsp")
                    ) : (
                      <NoValue />
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </Section>
  );
}

const STEP_CHIP: Readonly<Partial<Record<ApprovalStep["status"], string>>> = {
  ACTIVE: "Pending approval",
  APPROVED: "Approved",
  REJECTED: "Rejected",
  VOIDED: "Void",
};

function Routing({ approval }: { readonly approval: Approval }) {
  return (
    <ol
      aria-label={t("modifications.detail.routing")}
      data-testid="SF-07-routing"
      className="flex flex-col gap-2 text-body-sm"
    >
      {approval.steps.map((step) => {
        const chip = STEP_CHIP[step.status];
        return (
          <li key={step.step_no} className="flex flex-col gap-0.5">
            <span className="flex flex-wrap items-center gap-2 text-fg-1">
              <span>{`${step.name} · ${permissionLabel(step.required_permission)}`}</span>
              {chip === undefined ? (
                <span className="text-fg-3">
                  {t(`modifications.detail.stepStatus.${step.status}`)}
                </span>
              ) : (
                <StatusChip status={chip} />
              )}
            </span>
            {step.decisions.map((decision) => (
              <span key={decision.id} className="flex flex-wrap gap-x-2 text-fg-2">
                <span>{decision.approver.display_name}</span>
                <span>{formatTimestamp(decision.decided_at)}</span>
                {decision.comment === null ? null : <q>{decision.comment}</q>}
              </span>
            ))}
          </li>
        );
      })}
    </ol>
  );
}

function StatusSteps({ status }: { readonly status: string }) {
  // SCREENS §7.10 "Pending approval": every step complete, step 5 captioned with the status.
  const steps: Step[] = WIZARD_STEPS.map((id) => ({
    id,
    label: t(`modifications.wizard.steps.${id}`),
    state: "complete",
    caption: id === "submit" ? status : undefined,
  }));
  return (
    <div data-testid="SF-07-stepper">
      <Stepper label={t("modifications.wizard.stepper")} steps={steps} currentId="submit" />
    </div>
  );
}

interface DetailProps {
  readonly base: WizardBase;
  readonly row: Modification;
  /** The session may prepare modifications: withdraw and edit a submitted one. */
  readonly canPrepare: boolean;
  readonly viewerId: string | null;
}

function ReadOnlyDetail({ base, row, canPrepare, viewerId }: DetailProps) {
  const { contract } = base;
  const location = useLocation();
  const navigate = useNavigate();
  const stays = usePageStays();
  const toast = useToast();
  const built = useBuiltPaths();
  const ctxSearch = contextSearch(location.search);
  const [dialog, setDialog] = useState<"withdraw" | "edit" | "revise" | null>(null);
  const [reason, setReason] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [problem, setProblem] = useState<Failure | null>(null);

  const requestId = row.approval_request_id;
  const queryClient = useQueryClient();
  // Both commands end the pending request, so the lists and the request are read again. `/withdraw`
  // answers the row as `GET` does, with its stored preview (04 §16.14 rev 1.188, item
  // MOD-ANSWER-PREVIEW-1): the row is taken from its answer. An edit clears the preview and the
  // proposal, and the wizard it opens reads the row.
  const withdrawCommand = useCommand<Modification>({
    method: "POST",
    path: `${modificationPath(row.id)}/withdraw`,
    invalidates: [...MODIFICATION_LIST_KEYS, approvalKey(requestId ?? "")],
  });
  const editCommand = useCommand<Modification>({
    method: "PATCH",
    path: modificationPath(row.id),
    invalidates: [...MODIFICATION_RECORD_KEYS, approvalKey(requestId ?? "")],
  });
  const working = withdrawCommand.pending || editCommand.pending;
  const approval = useQuery({
    queryKey: approvalKey(requestId ?? ""),
    queryFn: () => fetchApproval(requestId ?? ""),
    enabled: requestId !== null,
    retry: false,
  });
  const judgements = useQuery({
    queryKey: modificationJudgementsKey(row.id),
    queryFn: () => fetchModificationJudgements(row.id),
  });
  const linkedJudgements: readonly Judgement[] = judgements.data ?? [];
  const judgementsId = useId();
  // SCREENS §7.8 "Linked requests": the estimate versions created inside the modification, each
  // approved before its submission (04 §16.14 rev 1.210), above the judgement records.
  const linkedVersions = linkedVersionsOf(row);
  const versionsId = useId();
  const chip = chipFor("E-26", row.status);
  const statusText = chip === null ? row.status : t(statusMessageKey(chip.status));
  const departing = departures(row.proposed_treatments, row.chosen_treatments);
  const submitted = row.status === "SUBMITTED";
  const rejected = row.status === "REJECTED";
  // Only the preparer of the request may withdraw it (PRD SM-01).
  const isPreparer = viewerId !== null && approval.data?.preparer.id === viewerId;
  // "Revise" is the API's edit of a rejected row: it asks `modification.create` for the contract's
  // entity, so the access module is asked for that entity (SCREENS §0.6 SCR-PERM-02 (a)).
  const access = useAccess();
  const canRevise =
    rejected && access.holds(MODIFICATION_CREATE_PERMISSION, contract.contracting_entity);
  const reference = row.reference ?? row.modification_no;

  const close = () => {
    setDialog(null);
    setReason("");
    setAttempted(false);
    setProblem(null);
  };
  const withdraw = async () => {
    setAttempted(true);
    if (reasonError(reason, 1) !== null) {
      return;
    }
    setProblem(null);
    const outcome = await withdrawCommand.submit({
      comment: reason.trim(),
    } satisfies ModificationWithdrawBody);
    if (outcome.kind !== "succeeded") {
      setProblem(outcome.kind === "failed" ? outcome.problem : "unreached");
      return;
    }
    toast.show({ tone: "positive", message: t("modifications.detail.withdrawn") });
    close();
    if (outcome.data === null) {
      void queryClient.invalidateQueries({ queryKey: modificationKey(row.id) });
    } else {
      queryClient.setQueryData(modificationKey(row.id), outcome.data);
    }
  };
  const edit = async () => {
    setProblem(null);
    // BR-PLT-05: an edit of a submitted row returns it to Draft and voids its request; the empty
    // body changes no member. "Revise" is the same edit of a rejected row (PRD SM-03 REJECTED →
    // DRAFT): the row returns to Draft and its request, which was decided, stays as it is.
    const outcome = await editCommand.submit({} satisfies ModificationUpdateBody);
    if (outcome.kind !== "succeeded") {
      setProblem(outcome.kind === "failed" ? outcome.problem : "unreached");
      return;
    }
    // The answer of an edit the member has walked away from opens nothing: the write names this
    // page's own path and would take them back to it (DG-FE-03 rule (3), rev 1.230).
    if (!stays()) {
      return;
    }
    close();
    void navigate(`${location.pathname}${withParams(location.search, { step: "change" })}`, {
      replace: true,
    });
  };

  const flags = [
    ...new Set([
      ...(approval.data?.flags ?? []),
      ...(departing.length > 0 ? ["TREATMENT_OVERRIDE"] : []),
    ]),
  ];
  // The request of the banner of a rejected modification. A request the reader cannot open — the
  // read failed, and "Approval" says so — is not offered.
  const requestLink =
    requestId !== null && !approval.isError && built.has(REQUEST_ROUTE) ? (
      <Link
        to={`${requestRoute(requestId)}${ctxSearch}`}
        className="text-body-sm text-accent-fg hover:underline"
      >
        {t("contracts.workbench.banner.viewRequest")}
      </Link>
    ) : null;
  const actions =
    submitted && canPrepare ? (
      <>
        <Button variant="secondary" size="sm" onClick={() => setDialog("edit")}>
          {t("modifications.detail.edit")}
        </Button>
        {isPreparer ? (
          <Button variant="secondary" size="sm" onClick={() => setDialog("withdraw")}>
            {t("modifications.detail.withdraw")}
          </Button>
        ) : null}
      </>
    ) : null;

  return (
    <ModificationFrame
      testId="SF-07-detail-page"
      contract={contract}
      ctxSearch={ctxSearch}
      title={t("modifications.detail.heading", { reference })}
      crumb={reference}
      status={row.status}
      meta={t("modifications.detail.meta", {
        kind: t(`modification.kind.${row.kind}`),
        date: formatDate(row.effective_date),
      })}
      actions={actions}
    >
      {flags.length === 0 ? null : (
        <ul aria-label={t("modifications.wizard.summary.flags")} className="flex flex-wrap gap-2">
          {flags.map((flag) => (
            <li key={flag}>
              <OutlineChip label={flagLabel(flag)} />
            </li>
          ))}
        </ul>
      )}
      {rejected ? (
        // SCREENS §7.9 (rev 1.65): the banner is the one place of "Revise"; the routing with the
        // decision and its comment stays in "Approval".
        <Banner
          tone="info"
          title={t("modifications.detail.rejected", { reference })}
          announce="static"
          headingLevel={2}
          actions={
            requestLink === null && !canRevise ? undefined : (
              <>
                {requestLink}
                {canRevise ? (
                  <Button variant="link" onClick={() => setDialog("revise")}>
                    {t("modifications.detail.revise")}
                  </Button>
                ) : null}
              </>
            )
          }
        />
      ) : null}
      {row.status === "DRAFT" ? (
        <DraftRequestNotice request={approval.data} ctxSearch={ctxSearch} />
      ) : null}
      {submitted ? <StatusSteps status={statusText} /> : null}
      <ChangeSection row={row} />
      <AnswersSection row={row} />
      <TreatmentsSection row={row} />
      <Section title={t("modifications.detail.preview")} testId="SF-07-section-preview">
        {!holdsStoredPreview(row) ? (
          <p className="text-body-sm text-fg-2">{t("modifications.detail.noPreview")}</p>
        ) : (
          <>
            {row.impact_preview_sha256 === null ? null : (
              <p className="text-body-sm text-fg-2">
                {t("modifications.detail.snapshot", {
                  hash: row.impact_preview_sha256.slice(0, 12),
                })}
              </p>
            )}
            {row.impact_preview === null ? (
              // SCREENS §7.9 (rev 1.77; 04 §16.10 rev 1.300): a preview is stored and this reader is
              // not shown it. Before, the section told that reader that none was stored.
              <PreviewWithheld row={row} />
            ) : (
              <ModificationImpact
                summary={row.impact_preview}
                currency={row.currency}
                contextPeriod={new URLSearchParams(location.search).get("period")}
                periodLabel={base.periodLabel}
                added={addedKeys(row)}
                headingLevel={3}
                // The approval is still to come for a draft and for a pending request: only then can
                // its entries differ from the ones previewed (SCREENS §7.7 rev 1.52).
                latestPostablePeriod={
                  row.status === "DRAFT" || row.status === "SUBMITTED"
                    ? base.latestPostablePeriod
                    : undefined
                }
              />
            )}
          </>
        )}
      </Section>
      <Section title={t("modifications.detail.approval")} testId="SF-07-section-approval">
        {requestId === null ? (
          <p className="text-body-sm text-fg-2">{t("modifications.detail.noRequest")}</p>
        ) : approval.isPending ? (
          <Skeleton region={t("modifications.detail.approval")} shape="rows" count={2} />
        ) : approval.isError ? (
          <p className="text-body-sm text-fg-2">{t("modifications.detail.requestUnreadable")}</p>
        ) : (
          <>
            <p className="flex flex-wrap items-center gap-2 text-body-sm text-fg-2">
              {built.has(REQUEST_ROUTE) ? (
                <Link
                  to={requestRoute(approval.data.id)}
                  className="font-mono text-mono-sm text-fg-1 underline decoration-dotted underline-offset-4 hover:decoration-solid"
                >
                  {approval.data.request_no}
                </Link>
              ) : (
                <span className="font-mono text-mono-sm text-fg-1">{approval.data.request_no}</span>
              )}
              <span>
                {t("modifications.detail.submittedAt", {
                  at: formatTimestamp(approval.data.submitted_at),
                })}
              </span>
            </p>
            <Routing approval={approval.data} />
          </>
        )}
        <h3 id={judgementsId} className="text-title-sm text-fg-1">
          {t("modifications.detail.linked")}
        </h3>
        {linkedVersions.length === 0 ? null : (
          <>
            <h4 id={versionsId} className="text-body-sm font-medium text-fg-1">
              {t("modifications.wizard.linked.versions")}
            </h4>
            <LinkedVersionsTable
              contractId={contract.id}
              versions={linkedVersions}
              labelledBy={versionsId}
              ctxSearch={ctxSearch}
              requests
            />
          </>
        )}
        {linkedJudgements.length === 0 ? (
          <p className="text-body-sm text-fg-2">{t("modifications.wizard.linked.none")}</p>
        ) : (
          <JudgementTable judgements={linkedJudgements} labelledBy={judgementsId} />
        )}
      </Section>
      {row.status === "APPLIED" ? (
        <Section title={t("modifications.detail.applied")} testId="SF-07-section-applied">
          <p className="text-body-sm text-fg-2">
            {row.approved_at === null
              ? t("modifications.detail.appliedNoDate")
              : row.approver === null
                ? t("modifications.detail.approvedAt", { at: formatTimestamp(row.approved_at) })
                : t("modifications.detail.approvedBy", {
                    at: formatTimestamp(row.approved_at),
                    name: row.approver.display_name,
                  })}
          </p>
          <ul className="flex flex-wrap gap-4 text-body-sm">
            <li>
              <Link
                to={`/contracts/${contract.id}/history${withParams(ctxSearch, { view: "versions" })}`}
                className="text-accent-fg hover:text-accent-fg-hover hover:underline"
              >
                {t("modifications.detail.versionsLink")}
              </Link>
            </li>
            {built.has(REPORT_ROUTE) && row.reference !== null ? (
              <li>
                <Link
                  to={`/reports/${MODIFICATION_REGISTER}?f.reference=is:${encodeURIComponent(row.reference)}`}
                  className="text-accent-fg hover:text-accent-fg-hover hover:underline"
                >
                  {t("modifications.detail.registerLink")}
                </Link>
              </li>
            ) : null}
          </ul>
        </Section>
      ) : null}
      <Modal
        open={dialog === "withdraw"}
        variant="form"
        title={t("modifications.detail.withdraw")}
        description={t("modifications.detail.withdrawDescription")}
        primaryAction={{
          label: t("modifications.detail.withdraw"),
          onAction: () => void withdraw(),
        }}
        submitting={working}
        onClose={close}
        testId="SF-07-dialog-withdraw"
      >
        <ProblemNotice problem={problem} />
        <ReasonField
          name="withdraw-comment"
          label={t("modifications.detail.withdrawComment")}
          value={reason}
          onChange={setReason}
          minimum={1}
          showError={attempted}
        />
      </Modal>
      <Modal
        open={dialog === "edit"}
        variant="confirmation"
        title={t("modifications.detail.editTitle")}
        description={t("modifications.detail.editDescription")}
        primaryAction={{ label: t("modifications.detail.edit"), onAction: () => void edit() }}
        submitting={working}
        onClose={close}
        testId="SF-07-dialog-edit"
      >
        <ProblemNotice problem={problem} />
      </Modal>
      <Modal
        open={dialog === "revise"}
        variant="confirmation"
        title={t("modifications.detail.reviseTitle")}
        description={t("modifications.detail.reviseDescription")}
        primaryAction={{ label: t("modifications.detail.revise"), onAction: () => void edit() }}
        submitting={working}
        onClose={close}
        testId="SF-07-dialog-revise"
      >
        <ProblemNotice problem={problem} />
      </Modal>
    </ModificationFrame>
  );
}

export function ModificationDetail() {
  const me = useMe();
  const params = useParams();
  const contractId = params.contractId ?? "";
  const modificationId = params.modificationId ?? "";
  const location = useLocation();
  const navigate = useNavigate();
  const ctxSearch = contextSearch(location.search);
  const permissions = me.data?.permissions ?? [];
  const allowed = permissions.includes(CONTRACT_READ);
  const state = useWizardBase(contractId, allowed);
  const modification = useQuery({
    queryKey: modificationKey(modificationId),
    queryFn: () => fetchModification(modificationId),
    enabled: allowed,
    retry: (count, error) => !(error instanceof ApiProblem && error.status === 404) && count < 2,
  });
  const base = state.kind === "ready" ? state.base : null;
  const row = modification.data;
  const title = t("modifications.detail.title");
  const missing =
    (modification.isError &&
      modification.error instanceof ApiProblem &&
      modification.error.status === 404) ||
    state.kind === "not-found" ||
    (row !== undefined && row.contract_id !== contractId);

  if (base !== null && row !== undefined && !missing) {
    const canPrepare = permissions.includes(MODIFICATION_CREATE_PERMISSION);
    return row.status === "DRAFT" && canPrepare ? (
      <DraftWizard base={base} modification={row} permissions={permissions} />
    ) : (
      <ReadOnlyDetail
        base={base}
        row={row}
        canPrepare={canPrepare}
        viewerId={me.data?.user.id ?? null}
      />
    );
  }

  let body: ReactNode;
  if (me.isError) {
    body = <Banner tone="negative" title={me.error.message} />;
  } else if (me.data === undefined) {
    body = <Skeleton region={title} shape="rows" count={8} />;
  } else if (!allowed) {
    body = (
      <EmptyState
        title={t("settings.access.title", { area: t("modifications.access.area") })}
        description={t("settings.access.description", {
          permission: t("settings.access.permission.contractRead"),
        })}
        headingLevel={2}
      />
    );
  } else if (missing) {
    // SCREENS §7.10, SCR-ST-07.
    body = (
      <EmptyState
        title={t("modifications.detail.notFound")}
        description={t("errors.notFound.description")}
        headingLevel={2}
        action={{
          label: t("contracts.workbench.goToContracts"),
          onAction: () => void navigate(`/contracts${ctxSearch}`),
        }}
      />
    );
  } else if (modification.isError || state.kind === "error") {
    body = (
      <LoadError
        title={t("modifications.detail.loadError")}
        problem={
          modification.isError ? modification.error : state.kind === "error" ? state.error : null
        }
        onRetry={() => {
          if (modification.isError) {
            void modification.refetch();
          }
          if (state.kind === "error") {
            state.retry();
          }
        }}
      />
    );
  } else {
    body = <Skeleton region={title} shape="rows" count={8} />;
  }
  return (
    <ModificationFrame
      testId="SF-07-detail-page"
      contract={base?.contract ?? null}
      ctxSearch={ctxSearch}
      title={title}
    >
      {body}
    </ModificationFrame>
  );
}
