// SF-20:new: bounded PDF upload, idempotent extraction submission and resumable job navigation.
import { useEffect, useRef, useState } from "react";
import { useNavigate, useSearchParams } from "react-router";

import { ProposalBlock } from "../../components/ai/ProposalBlock";
import { AccessLimited } from "../../components/feedback/AccessLimited";
import { Banner } from "../../components/feedback/Banner";
import { EmptyState } from "../../components/feedback/EmptyState";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { Button } from "../../components/ui/Button";
import { useAccess } from "../../lib/access";
import { useCommand, useCommandKeys } from "../../lib/api/commands";
import { isTerminal, useJob } from "../../lib/api/jobs";
import { ApiProblem, parseProblem } from "../../lib/api/problems";
import { AI_REVIEW_ROUTE, AI_USE_PERMISSION, submitExtraction } from "../../lib/api/queries/ai";
import { useMe } from "../../lib/api/queries/me";
import { uploadFile } from "../../lib/api/queries/ssp-books";
import { queryKeys } from "../../lib/api/query-keys";
import { t } from "../../lib/i18n/t";

const PDF_LIMIT = 25 * 1024 * 1024;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function NewContractReview() {
  const access = useAccess();
  const me = useMe();
  const allowed = access.holdsAnywhere(AI_USE_PERMISSION);
  const navigate = useNavigate();
  const [search, setSearch] = useSearchParams();
  const jobId = search.get("job");
  const validJobId = jobId !== null && UUID.test(jobId) ? jobId : null;
  const job = useJob(allowed ? validJobId : null);
  const keys = useCommandKeys();
  const [file, setFile] = useState<File | null>(null);
  const uploaded = useRef<{ file: File; id: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const active = useRef(true);
  const [error, setError] = useState<string | null>(null);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const input = useRef<HTMLInputElement | null>(null);
  useEffect(() => {
    active.current = true;
    return () => {
      active.current = false;
    };
  }, []);
  const result = job.data?.result?.proposal_id;
  const completedProposal =
    job.data?.kind === "AI_TASK" &&
    job.data.state === "SUCCEEDED" &&
    typeof result === "string" &&
    UUID.test(result)
      ? result
      : null;
  useEffect(() => {
    if (completedProposal !== null)
      void navigate(`${AI_REVIEW_ROUTE}/${completedProposal}`, { replace: true });
  }, [completedProposal, navigate]);
  const cancel = useCommand({
    method: "POST",
    path: `/api/v1/jobs/${validJobId ?? ""}/cancel`,
    invalidates: validJobId === null ? [] : [queryKeys.job(validJobId)],
  });
  const canCancel =
    job.data?.kind === "AI_TASK" &&
    !isTerminal(job.data) &&
    job.data.created_by.id === me.data?.user.id &&
    !cancel.pending;
  const start = async () => {
    if (inFlight.current || jobId !== null || !allowed || !me.data?.tenant_settings.ai_enabled)
      return;
    setProblem(null);
    setError(null);
    if (file === null) {
      setError(t("ai.review.new.chooseRequired"));
      return;
    }
    if (
      file.size === 0 ||
      file.size > PDF_LIMIT ||
      !/\.pdf$/i.test(file.name) ||
      (file.type !== "" && file.type !== "application/pdf")
    ) {
      setError(t("ai.review.new.fileRules"));
      return;
    }
    inFlight.current = true;
    setBusy(true);
    try {
      let stored = uploaded.current;
      if (stored?.file !== file) {
        const saved = await uploadFile(keys, "ATTACHMENT", file);
        if (!active.current) return;
        stored = { file, id: saved.id };
        uploaded.current = stored;
      }
      const response = await submitExtraction(keys, stored.id);
      if (!active.current) return;
      if (!response.ok) {
        setProblem(response.problem);
        return;
      }
      if (!UUID.test(response.data.id) || response.data.kind !== "AI_TASK") {
        setError(t("ai.review.new.invalidJob"));
        return;
      }
      setSearch({ job: response.data.id }, { replace: true });
    } catch (caught) {
      if (!active.current) return;
      if (caught instanceof ApiProblem) setProblem(caught);
      else setError(t("ai.review.unreached"));
    } finally {
      inFlight.current = false;
      if (active.current) setBusy(false);
    }
  };
  if (me.isPending) return <Skeleton region={t("ai.review.new.title")} />;
  if (!allowed)
    return <AccessLimited area={t("ai.review.new.title")} permissions={[AI_USE_PERMISSION]} />;
  const enabled = me.data?.tenant_settings.ai_enabled === true;
  const failed =
    job.isError ||
    (job.data !== undefined &&
      (job.data.kind !== "AI_TASK" || (isTerminal(job.data) && completedProposal === null)));
  return (
    <div
      className="flex max-w-[var(--content-max-form)] flex-col gap-4"
      data-testid="SF-20-new-page"
    >
      <h1 className="text-title-lg text-fg-1">{t("ai.review.new.title")}</h1>
      <p className="text-body text-fg-2">{t("ai.review.new.description")}</p>
      <RefusalBanner problem={problem} />
      {error === null ? null : <Banner tone="negative" title={error} />}
      {jobId !== null ? (
        <>
          {validJobId === null ? (
            <Banner tone="negative" title={t("ai.review.new.invalidJob")} />
          ) : job.data?.state === "CANCELLED" ? (
            <Banner tone="info" title={t("ai.review.new.cancelled")} />
          ) : (
            <ProposalBlock
              state={failed ? "failed" : "generating"}
              source={t("ai.review.new.title")}
              onCancel={
                canCancel
                  ? () => {
                      setError(null);
                      void cancel.submit({}).then((outcome) => {
                        if (active.current && outcome.kind === "network-error")
                          setError(t("ai.review.unreached"));
                      });
                    }
                  : undefined
              }
            />
          )}
          <RefusalBanner problem={cancel.problem} conflict={cancel.banner} />
          {job.data?.problem ? (
            <RefusalBanner
              problem={parseProblem(job.data.problem, {
                status: job.data.problem.status,
                statusText: job.data.problem.title,
              })}
            />
          ) : null}
          {job.isError ? (
            <Button
              onClick={() => {
                void job.refetch();
              }}
            >
              {t("ai.review.reload")}
            </Button>
          ) : null}
          {failed || validJobId === null ? (
            <Button
              onClick={() => {
                setSearch({});
                keys.clear();
              }}
            >
              {t("ai.review.new.another")}
            </Button>
          ) : null}
        </>
      ) : !enabled ? (
        <EmptyState
          title={t("ai.review.new.disabled")}
          description={t("ai.review.new.disabledHelp")}
        />
      ) : (
        <>
          <input
            ref={input}
            type="file"
            accept="application/pdf,.pdf"
            className="sr-only"
            aria-label={t("ai.review.new.choose")}
            disabled={busy}
            onChange={(event) => {
              setFile(event.target.files?.[0] ?? null);
              uploaded.current = null;
              keys.clear();
              setError(null);
              setProblem(null);
            }}
          />
          <div className="rounded-lg border border-dashed border-hairline p-[var(--panel-pad)]">
            <Button
              disabledReason={busy ? t("ai.review.new.working") : undefined}
              onClick={() => input.current?.click()}
            >
              {t("ai.review.new.choose")}
            </Button>
            <p className="mt-2 text-body-sm text-fg-2">{t("ai.review.new.fileRules")}</p>
            {file === null ? null : <p className="mt-2 break-words text-body">{file.name}</p>}
          </div>
          <Button
            variant="primary"
            loading={busy}
            onClick={() => {
              void start();
            }}
          >
            {t("ai.review.new.start")}
          </Button>
        </>
      )}
    </div>
  );
}
