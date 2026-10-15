// SF-20 retained extraction evidence. Commands use the read ETag; original text is never HTML.
import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useParams, useSearchParams } from "react-router";

import { ProposalBlock } from "../../components/ai/ProposalBlock";
import { AccessLimited } from "../../components/feedback/AccessLimited";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { Field, controlClass } from "../../components/form/Field";
import { ReasonField, reasonError } from "../../components/form/ReasonField";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { useAccess } from "../../lib/access";
import { useCommand } from "../../lib/api/commands";
import { ApiProblem } from "../../lib/api/problems";
import {
  AI_USE_PERMISSION,
  type AcceptedDraft,
  documentTextKey,
  type DocumentText,
  type ExtractionProposal,
  fetchDocumentText,
  fetchProposal,
  proposalKey,
  proposalPath,
} from "../../lib/api/queries/ai";
import { queryKey } from "../../lib/api/query-keys";
import type { DraftForm } from "../../lib/forms/contract";
import { formatTimestamp, instantMs } from "../../lib/format";
import { hasMessage, t } from "../../lib/i18n/t";
import { ReviewedContractDraft } from "./draft-form";
import {
  fieldChoice,
  prepareReview,
  resumeDraft,
  type FieldChoice,
  type PreparedReview,
  type Decision,
} from "./review-decisions";
import { ReviewPanes } from "./review-panes";

interface Citation {
  readonly page: number;
  readonly start: number;
  readonly end: number;
}

function citationOf(value: unknown, source: string): Citation | null {
  if (typeof value !== "object" || value === null) return null;
  const item = value as Record<string, unknown>;
  if (
    item.ref_type !== "document" ||
    item.ref_id !== source ||
    !Number.isSafeInteger(item.page) ||
    !Number.isSafeInteger(item.char_start) ||
    !Number.isSafeInteger(item.char_end)
  )
    return null;
  const page = item.page as number;
  const start = item.char_start as number;
  const end = item.char_end as number;
  return page > 0 && start >= 0 && end > start ? { page, start, end } : null;
}

/** Python source offsets are Unicode code points, not JavaScript UTF-16 code units. */
export function citedParts(text: string, start: number, end: number): readonly string[] | null {
  const points = Array.from(text);
  if (
    !Number.isSafeInteger(start) ||
    !Number.isSafeInteger(end) ||
    start < 0 ||
    end <= start ||
    end > points.length
  )
    return null;
  return [
    points.slice(0, start).join(""),
    points.slice(start, end).join(""),
    points.slice(end).join(""),
  ];
}

function labelOf(path: unknown): string {
  if (typeof path !== "string") return t("ai.review.field");
  const key = `ai.review.field.${path}`;
  return hasMessage(key) ? t(key) : path;
}

function valueText(value: unknown): string {
  return typeof value === "string" ? value : (JSON.stringify(value) ?? "");
}

function ReviewEvidence({
  proposal,
  etag,
  text,
  canCreate,
}: {
  readonly proposal: ExtractionProposal;
  readonly etag: string | null;
  readonly text: DocumentText | undefined;
  readonly canCreate: boolean;
}) {
  const [search, setSearch] = useSearchParams();
  const pane = search.get("pane") === "fields" ? "fields" : "document";
  const changePane = (next: string) => {
    setSearch(
      (current) => {
        const updated = new URLSearchParams(current);
        updated.set("pane", next);
        return updated;
      },
      { replace: true },
    );
  };
  const [selected, setSelected] = useState<{ citation: Citation; label: string } | null>(null);
  const [choices, setChoices] = useState(() =>
    proposal.content.map((field) =>
      fieldChoice(field, citationOf(field.citation, proposal.file_object_id) !== null),
    ),
  );
  const [dateTarget, setDateTarget] = useState<"inception_date" | "signature_date" | null>(null);
  const [reviewError, setReviewError] = useState<string | null>(null);
  const [prepared, setPrepared] = useState<{ review: PreparedReview; etag: string } | null>(null);
  const [savedDraft, setSavedDraft] = useState<{ review: PreparedReview; form: DraftForm } | null>(
    null,
  );
  const accept = useCommand<AcceptedDraft>({
    method: "POST",
    path: `${proposalPath(proposal.id)}/accept`,
    invalidates: [queryKey("ai-proposals", "tenant"), queryKey("contracts", "tenant")],
  });
  const updateChoice = (index: number, update: Partial<FieldChoice>) => {
    setChoices((current) =>
      current.map((choice, at) => (at === index ? { ...choice, ...update } : choice)),
    );
    setReviewError(null);
  };
  const trigger = useRef<HTMLButtonElement | null>(null);
  const triggerIndex = useRef<number | null>(null);
  const returning = useRef(false);
  const highlight = useRef<HTMLElement | null>(null);
  useEffect(() => {
    if (returning.current && pane === "fields") {
      trigger.current?.focus();
      returning.current = false;
    } else if (selected !== null && pane === "document") {
      highlight.current?.focus();
      highlight.current?.scrollIntoView?.({ block: "nearest" });
    }
  }, [selected, pane]);
  useEffect(() => {
    const returnToCitation = (event: KeyboardEvent) => {
      if (event.key === "Escape" && document.activeElement === highlight.current) {
        event.preventDefault();
        returning.current = true;
        setSelected(null);
        changePane("fields");
      }
    };
    document.addEventListener("keydown", returnToCitation);
    return () => document.removeEventListener("keydown", returnToCitation);
  });
  const [rejecting, setRejecting] = useState(false);
  const [reason, setReason] = useState("");
  const [attempted, setAttempted] = useState(false);
  const [unreached, setUnreached] = useState(false);
  const command = useCommand<ExtractionProposal>({
    method: "POST",
    path: `${proposalPath(proposal.id)}/reject`,
    invalidates: [queryKey("ai-proposals", "tenant")],
  });
  const expired =
    proposal.status === "expired" ||
    (proposal.status === "proposed" && instantMs(proposal.expires_at) <= Date.now());
  const canReject = proposal.status === "proposed" && !expired && etag !== null;
  const reject = async () => {
    setAttempted(true);
    if (!canReject || reasonError(reason) !== null) return;
    setUnreached(false);
    const result = await command.submit({ reason: reason.trim() }, { ifMatch: etag });
    if (result.kind === "succeeded") setRejecting(false);
    else setUnreached(result.kind === "network-error");
  };
  const editable = canReject && canCreate;
  const prepare = () => {
    if (!editable || etag === null || text === undefined) return;
    for (const [index, field] of proposal.content.entries()) {
      if (choices[index]?.decision === "REJECT") continue;
      const cite = citationOf(field.citation, proposal.file_object_id);
      const page = text.pages.find((item) => item.page_no === cite?.page);
      if (
        cite === null ||
        page === undefined ||
        citedParts(page.text, cite.start, cite.end) === null
      ) {
        setReviewError(t("ai.review.decision.error.citation", { field: labelOf(field.path) }));
        return;
      }
    }
    const result = prepareReview(proposal, choices, dateTarget);
    if (!result.ok) {
      setReviewError(
        t(`ai.review.decision.error.${result.error}`, { field: labelOf(result.path) }),
      );
      return;
    }
    const review =
      savedDraft === null
        ? result.review
        : resumeDraft(savedDraft.review, savedDraft.form, result.review);
    setPrepared({ review, etag });
  };
  if (prepared !== null && proposal.status === "proposed")
    return (
      <ReviewedContractDraft
        initial={prepared.review.initial}
        onReview={(form) => {
          setSavedDraft({ review: prepared.review, form });
          setPrepared(null);
        }}
        submit={(draft) =>
          accept.submit(
            {
              command: "contract.create_draft",
              entity_code: draft.contracting_entity_code,
              draft,
              field_decisions: prepared.review.decisions,
              header_bindings: prepared.review.headers,
              line_bindings: prepared.review.lines,
            },
            { ifMatch: prepared.etag },
          )
        }
      />
    );
  return (
    <>
      {savedDraft === null ? null : (
        <p className="text-body-sm text-fg-2">{t("ai.review.draft.saved")}</p>
      )}
      {reviewError === null ? null : <Banner tone="negative" title={reviewError} />}
      {editable ? (
        <Button
          variant="primary"
          disabledReason={text === undefined ? t("ai.review.decision.needText") : undefined}
          onClick={prepare}
        >
          {t("ai.review.decision.continue")}
        </Button>
      ) : null}
      <RefusalBanner problem={command.problem} conflict={command.banner} />
      {expired ? (
        <Banner
          tone="warning"
          title={t("ai.review.expired", { at: formatTimestamp(proposal.expires_at) })}
        />
      ) : null}
      {canReject ? (
        <div>
          <Button onClick={() => setRejecting(true)}>{t("ai.review.reject")}</Button>
        </div>
      ) : null}
      {proposal.status === "accepted" &&
      proposal.accepted_object_type === "contract" &&
      proposal.accepted_object_id !== null ? (
        <Link
          className="text-accent-fg hover:underline"
          to={`/contracts/${proposal.accepted_object_id}/obligations`}
        >
          {t("ai.review.openDraft")}
        </Link>
      ) : null}
      <ReviewPanes
        pane={pane}
        onChange={changePane}
        document={
          <section
            aria-label={t("ai.review.document")}
            data-testid="SF-20-pane-document"
            className="min-w-0 rounded-lg border border-hairline p-[var(--panel-pad)]"
          >
            <h2 className="text-title-sm text-fg-1">{t("ai.review.document")}</h2>
            {text?.pages.map((page) => {
              const active = selected?.citation.page === page.page_no ? selected : null;
              const parts =
                active === null
                  ? null
                  : citedParts(page.text, active.citation.start, active.citation.end);
              return (
                <section
                  key={page.page_no}
                  aria-label={t("ai.review.page", { page: page.page_no })}
                  className="mt-4"
                >
                  <h3 className="text-caption text-fg-3">
                    {t("ai.review.page", { page: page.page_no })}
                  </h3>
                  <div className="whitespace-pre-wrap break-words text-body text-fg-1">
                    {parts === null ? (
                      page.text
                    ) : (
                      <>
                        {parts[0]}
                        <mark
                          tabIndex={-1}
                          aria-label={t("ai.review.cited", { field: active?.label ?? "" })}
                          className="bg-accent-subtle text-fg-1"
                          ref={highlight}
                        >
                          {parts[1]}
                        </mark>
                        {parts[2]}
                      </>
                    )}
                  </div>
                </section>
              );
            })}
          </section>
        }
        fields={
          <ProposalBlock
            state={
              proposal.status === "accepted"
                ? "accepted"
                : proposal.status === "failed"
                  ? "failed"
                  : "ready"
            }
            source={formatTimestamp(proposal.created_at)}
            acceptedBy={proposal.accepted_by?.display_name}
          >
            {proposal.status === "rejected" ? (
              <p>
                {t("ai.review.rejected", {
                  by: proposal.rejected_by?.display_name ?? "",
                  reason: proposal.rejection_reason ?? "",
                })}
              </p>
            ) : null}
            {proposal.status === "accepted" && proposal.accepted_at !== null ? (
              <p>{t("ai.review.acceptedAt", { at: formatTimestamp(proposal.accepted_at) })}</p>
            ) : null}
            <dl className="flex flex-col gap-4">
              {proposal.content.map((field, index) => {
                const label = labelOf(field.path);
                const citation = citationOf(field.citation, proposal.file_object_id);
                const page = text?.pages.find((item) => item.page_no === citation?.page);
                const valid =
                  citation !== null &&
                  page !== undefined &&
                  citedParts(page.text, citation.start, citation.end) !== null;
                const recorded = proposal.field_decisions?.find(
                  (decision) => decision.path === field.path,
                );
                return (
                  <div key={`${String(field.path)}-${String(index)}`}>
                    <dt className="text-body-sm font-medium text-fg-1">{label}</dt>
                    <dd className="whitespace-pre-wrap break-words">{valueText(field.value)}</dd>
                    {typeof field.confidence === "string" ? (
                      <dd className="text-caption text-fg-3">
                        {t("ai.review.confidence", { value: field.confidence })}
                        {field.check === true ? ` · ${t("ai.review.check")}` : ""}
                      </dd>
                    ) : null}
                    {valid && citation !== null ? (
                      <dd>
                        <Button
                          variant="ghost"
                          size="sm"
                          ref={(element) => {
                            if (triggerIndex.current === index) trigger.current = element;
                          }}
                          onClick={(event) => {
                            trigger.current = event.currentTarget;
                            triggerIndex.current = index;
                            changePane("document");
                            setSelected({ citation, label });
                          }}
                        >
                          {t("ai.review.citation", {
                            page: citation.page,
                            start: citation.start,
                            end: citation.end,
                          })}
                        </Button>
                      </dd>
                    ) : null}
                    {editable && choices[index] !== undefined ? (
                      <dd className="mt-2 flex flex-col gap-2">
                        <fieldset className="flex flex-wrap gap-3">
                          <legend className="text-body-sm">
                            {t("ai.review.decision.for", { field: label })}
                          </legend>
                          {(["ACCEPT", "EDIT", "REJECT"] as const)
                            .filter((decision) => valid || decision === "REJECT")
                            .map((decision: Decision) => (
                              <label
                                key={decision}
                                className="flex items-center gap-1 text-body-sm"
                              >
                                <input
                                  type="radio"
                                  name={`decision-${String(index)}`}
                                  value={decision}
                                  checked={choices[index]?.decision === decision}
                                  onChange={() => updateChoice(index, { decision })}
                                />
                                {t(`ai.review.decision.${decision}`)}
                              </label>
                            ))}
                        </fieldset>
                        {choices[index]?.decision === "EDIT" ? (
                          <>
                            {typeof field.path === "string" && field.path.startsWith("lines.") ? (
                              <Field
                                name={`product-${String(index)}`}
                                label={t("ai.review.decision.product", { field: label })}
                              >
                                {(control) => (
                                  <input
                                    {...control}
                                    className={controlClass(false)}
                                    value={choices[index]?.product ?? ""}
                                    onChange={(event) =>
                                      updateChoice(index, { product: event.target.value })
                                    }
                                  />
                                )}
                              </Field>
                            ) : null}
                            <Field
                              name={`edit-${String(index)}`}
                              label={t("ai.review.decision.value", { field: label })}
                            >
                              {(control) => (
                                <input
                                  {...control}
                                  className={controlClass(false)}
                                  value={choices[index]?.value ?? ""}
                                  onChange={(event) =>
                                    updateChoice(index, { value: event.target.value })
                                  }
                                />
                              )}
                            </Field>
                          </>
                        ) : null}
                        {choices[index]?.decision === "EDIT" ||
                        choices[index]?.decision === "REJECT" ? (
                          <ReasonField
                            name={`reason-${String(index)}`}
                            label={t("ai.review.decision.reason", { field: label })}
                            value={choices[index]?.reason ?? ""}
                            onChange={(reason) => updateChoice(index, { reason })}
                          />
                        ) : null}
                        {field.path === "effective_date" &&
                        choices[index]?.decision !== "REJECT" ? (
                          <fieldset className="flex gap-3">
                            <legend>{t("ai.review.decision.dateTarget")}</legend>
                            {(["inception_date", "signature_date"] as const).map((target) => (
                              <label key={target}>
                                <input
                                  type="radio"
                                  name="effective-date-target"
                                  checked={dateTarget === target}
                                  onChange={() => setDateTarget(target)}
                                />
                                {t(`ai.review.decision.${target}`)}
                              </label>
                            ))}
                          </fieldset>
                        ) : null}
                      </dd>
                    ) : null}
                    {recorded === undefined ? null : (
                      <dd className="text-body-sm text-fg-2">
                        <p>{t("ai.review.decision", { decision: String(recorded.decision) })}</p>
                        {recorded.decision === "EDIT" ? <p>{valueText(recorded.value)}</p> : null}
                        {typeof recorded.reason === "string" ? <p>{recorded.reason}</p> : null}
                      </dd>
                    )}
                  </div>
                );
              })}
            </dl>
          </ProposalBlock>
        }
      />
      <Modal
        open={rejecting}
        variant="confirmation"
        title={t("ai.review.reject")}
        description={t("ai.review.rejectConsequence")}
        submitting={command.pending}
        primaryAction={{
          label: t("ai.review.reject"),
          destructive: true,
          onAction: () => {
            void reject();
          },
        }}
        onClose={() => {
          if (!command.pending) setRejecting(false);
        }}
      >
        <RefusalBanner problem={command.problem} conflict={command.banner} />
        {unreached ? <Banner tone="warning" title={t("ai.review.unreached")} /> : null}
        <ReasonField
          label={t("ai.review.reason")}
          value={reason}
          onChange={setReason}
          showError={attempted}
        />
      </Modal>
    </>
  );
}

export function ContractReview() {
  const { proposalId = "" } = useParams();
  const access = useAccess();
  const allowed = access.holdsAnywhere(AI_USE_PERMISSION);
  const read = useQuery({
    queryKey: proposalKey(proposalId),
    queryFn: () => fetchProposal(proposalId),
    enabled: allowed,
  });
  const proposal = read.data?.proposal;
  const document = useQuery({
    queryKey: documentTextKey(proposalId),
    queryFn: () => fetchDocumentText(proposalId),
    enabled: allowed && !read.isError && proposal?.kind === "CONTRACT_EXTRACTION",
  });
  if (!allowed)
    return <AccessLimited area={t("ai.review.title")} permissions={[AI_USE_PERMISSION]} />;
  if (read.isPending) return <Skeleton region={t("ai.review.title")} />;
  if (read.isError || proposal?.kind !== "CONTRACT_EXTRACTION")
    return (
      <EmptyState
        title={t("ai.review.notFound")}
        description={t("ai.review.readFailed")}
        action={{
          label: t("ai.review.reload"),
          onAction: () => {
            void read.refetch();
          },
        }}
      />
    );
  return (
    <div className="flex flex-col gap-4" data-testid="SF-20-page">
      <h1 className="text-title-lg text-fg-1">{t("ai.review.title")}</h1>
      {document.isPending ? <Skeleton region={t("ai.review.document")} /> : null}
      {document.isError ? (
        <Banner
          tone="negative"
          title={t("ai.review.documentFailed")}
          actions={
            <Button
              onClick={() => {
                void document.refetch();
              }}
            >
              {t("ai.review.reload")}
            </Button>
          }
        >
          {document.error instanceof ApiProblem
            ? document.error.message
            : t("ai.review.readFailed")}
        </Banner>
      ) : null}
      <ReviewEvidence
        key={proposal.id}
        proposal={proposal}
        etag={read.data.etag}
        text={document.isError ? undefined : document.data}
        canCreate={access.holdsAnywhere("contract.create")}
      />
    </div>
  );
}
