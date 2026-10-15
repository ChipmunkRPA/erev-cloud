// SF-15:ai: independent administrator approval and immediate emergency disable.
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { Link } from "react-router";
import { AccessLimited } from "../../components/feedback/AccessLimited";
import { Banner } from "../../components/feedback/Banner";
import { RefusalBanner } from "../../components/feedback/RefusalBanner";
import { Skeleton } from "../../components/feedback/Skeleton";
import { useToast } from "../../components/feedback/Toast";
import { Field, controlClass } from "../../components/form/Field";
import { ReasonField, reasonError } from "../../components/form/ReasonField";
import { Button } from "../../components/ui/Button";
import { Modal } from "../../components/ui/Modal";
import { useAccess } from "../../lib/access";
import { api, send, unwrap } from "../../lib/api/client";
import { useCommandKeys } from "../../lib/api/commands";
import { fetchJob, isTerminal } from "../../lib/api/jobs";
import { fetchListPage } from "../../lib/api/lists";
import type { RegistryParameter } from "../../lib/api/queries/policies";
import { ApiProblem, readProblem } from "../../lib/api/problems";
import {
  aiSettingsKey,
  aiSettingsVersionsKey,
  fetchAISettings,
  fetchAISettingsVersions,
  AI_SETTINGS_VERSIONS_PATH,
  type AISettingsVersion,
} from "../../lib/api/queries/ai-settings";
import { fetchApproval, requestRoute } from "../../lib/api/queries/approvals";
import { rowIfMatch } from "../../lib/api/queries/tenant";
import { useMe } from "../../lib/api/queries/me";
import { t } from "../../lib/i18n/t";
import { SettingsPageHeader } from "./index";
import { ratioToPercent } from "./workspace";

const PREFIX = "settings.aiSettings.";
const label = (key: string) => t(PREFIX + key);
const FIELDS = [
  ["ai.enabled", "enabled", "boolean"],
  ["ai.send_contract_text", "sendText", "boolean"],
  ["ai.model", "model", "text"],
  ["ai.monthly_token_budget", "budget", "integer"],
  ["ai.redact_contact_details", "redact", "boolean"],
  ["ai.anomaly.revenue_change_ratio", "revenueChange", "percent"],
  ["ai.anomaly.revenue_ahead_of_billing_days", "aheadDays", "integer"],
  ["ai.anomaly.allocation_adjustment_ratio", "allocation", "percent"],
] as const;
type Values = Record<string, string | boolean>;

/** Exact decimal shift; percentages never pass through binary floating point. */
export function aiPercentRatio(text: string, maximum: number): string | null {
  const value = text.trim();
  if (!/^\d+(\.\d+)?$/.test(value) || value.length > 100) return null;
  const [whole = "0", fraction = ""] = value.split(".");
  const n = BigInt(whole);
  if (n > BigInt(maximum) || (n === BigInt(maximum) && /[1-9]/.test(fraction))) return null;
  const digits = n.toString().padStart(3, "0");
  const tail = `${digits.slice(-2)}${fraction}`.replace(/0+$/, "");
  return `${digits.slice(0, -2)}${tail === "" ? "" : `.${tail}`}`;
}

export function aiStatement(values: Values): Record<string, string | boolean | number> {
  return Object.fromEntries(
    FIELDS.map(([code, key, kind]) => {
      const raw = values[code];
      if (kind === "boolean") {
        if (typeof raw !== "boolean") throw new Error(label(key));
        return [code, raw];
      }
      const text = typeof raw === "string" ? raw.trim() : "";
      if (kind === "text") {
        if (!text || text.includes("\0")) throw new Error(label("invalidModel"));
        return [code, text];
      }
      if (kind === "percent") {
        const ratio = aiPercentRatio(text, key === "revenueChange" ? 1000 : 100);
        if (ratio === null)
          throw new Error(label(key === "revenueChange" ? "invalidRevenue" : "invalidPercent"));
        return [code, ratio];
      }
      const integer = Number(text);
      if (
        !/^\d+$/.test(text) ||
        !Number.isSafeInteger(integer) ||
        (key === "aheadDays" && (integer < 1 || integer > 365))
      ) {
        throw new Error(label(key === "aheadDays" ? "invalidDays" : "invalidBudget"));
      }
      return [code, integer];
    }),
  );
}

async function loadForm() {
  const [status, versions, resolved] = await Promise.all([
    fetchAISettings(),
    Promise.all(
      ["DRAFT", "TESTED", "SUBMITTED"].map(
        async (status) => (await fetchAISettingsVersions({ status })).items,
      ),
    ),
    Promise.all(
      FIELDS.map(
        async ([code]) =>
          [
            code,
            (
              await unwrap(
                api.GET("/api/v1/policies/resolve", { params: { query: { key: code } } }),
              )
            ).value as unknown,
          ] as const,
      ),
    ),
  ]);
  const open = versions.flat();
  if (open.length > 1) throw new Error(label("multipleOpen"));
  const version = open[0];
  const stored = Object.fromEntries(resolved);
  const current = { ...stored, ...(version?.values ?? {}) };
  if ((version?.unset ?? []).length > 0) {
    const catalogue = await fetchListPage<RegistryParameter>(
      "/api/v1/registry/parameters",
      { category: "AI" },
      null,
    );
    for (const code of version?.unset ?? []) {
      const parameter = catalogue.items.find((item) => item.code === code);
      if (!parameter) throw new Error(label("invalidSettings"));
      current[code] = parameter.default_asc606;
    }
  }
  const values: Values = Object.fromEntries(
    FIELDS.map(([code, , kind]) => {
      const value = current[code];
      if (kind === "boolean") {
        if (typeof value !== "boolean") throw new Error(label("invalidSettings"));
        return [code, value];
      }
      if (typeof value !== "string" && typeof value !== "number")
        throw new Error(label("invalidSettings"));
      return [code, kind === "percent" ? ratioToPercent(String(value)) : String(value)];
    }),
  );
  const requestId = version?.pending_approval_request_id;
  let approval = null;
  if (requestId) {
    try {
      approval = await fetchApproval(requestId);
    } catch (error) {
      if (!(error instanceof ApiProblem) || ![403, 404].includes(error.status)) throw error;
    }
  }
  return { status, version, values, approval };
}

export function AISettings() {
  const me = useMe();
  const access = useAccess();
  const allowed = access.holdsForAll("settings.manage");
  return (
    <div className="flex w-full max-w-[var(--content-max-form)] flex-col gap-6 px-[var(--gutter)] py-6">
      <SettingsPageHeader title={label("title")} group="ai" />
      {me.isError ? (
        <Banner tone="negative" title={me.error.message} />
      ) : me.data === undefined ? (
        <Skeleton region={label("title")} shape="rows" count={8} />
      ) : !allowed ? (
        <AccessLimited area={label("title")} permissions={["settings.manage"]} />
      ) : (
        <SettingsData />
      )}
    </div>
  );
}

function SettingsData() {
  const data = useQuery({
    queryKey: aiSettingsVersionsKey({ view: "form" }),
    queryFn: loadForm,
    refetchOnWindowFocus: false,
    refetchOnReconnect: false,
  });
  if (data.isError) return <Banner tone="negative" title={data.error.message} />;
  if (!data.data) return <Skeleton region={label("title")} shape="rows" count={8} />;
  return (
    <SettingsForm
      key={`${data.data.version?.id ?? "new"}:${data.data.version?.row_version ?? 0}`}
      initial={data.data}
    />
  );
}

function SettingsForm({ initial }: { readonly initial: Awaited<ReturnType<typeof loadForm>> }) {
  const [values, setValues] = useState(initial.values);
  const [comment, setComment] = useState("");
  const [busy, setBusy] = useState(false);
  const [disabling, setDisabling] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [problem, setProblem] = useState<ApiProblem | null>(null);
  const [confirm, setConfirm] = useState(false);
  const [disableComment, setDisableComment] = useState("");
  const [retry, setRetry] = useState(false);
  const keys = useCommandKeys();
  const disableKeys = useCommandKeys();
  const queryClient = useQueryClient();
  const toast = useToast();
  const intent = useRef<{
    values: ReturnType<typeof aiStatement>;
    comment: string;
    id?: string;
    job?: string;
    etag?: string;
  } | null>(null);
  const submitted = initial.version?.status === "SUBMITTED";
  const requestId = initial.version?.pending_approval_request_id;
  async function refresh() {
    await Promise.all(
      [aiSettingsKey(), aiSettingsVersionsKey()].map((queryKey) =>
        queryClient.invalidateQueries({ queryKey: [queryKey[0]] }),
      ),
    );
    await queryClient.invalidateQueries({ queryKey: ["me"] });
  }
  function refused(e: unknown) {
    if (e instanceof ApiProblem) setProblem(e);
    else setError(e instanceof Error ? e.message : t("common.command.noAnswer"));
  }
  async function command<T>(
    method: "POST" | "PATCH",
    path: string,
    body: unknown,
    etag?: string,
  ): Promise<T> {
    const response = await keys.send(method, path, {
      body,
      keep: true,
      ...(etag ? { headers: { "If-Match": etag } } : {}),
    });
    if (!response.ok) throw await readProblem(response);
    return response.json() as Promise<T>;
  }
  async function submit() {
    if (busy || submitted) return;
    setError(null);
    setProblem(null);
    try {
      if (!intent.current) {
        const reason = reasonError(comment);
        if (reason !== null) throw new Error(reason);
        intent.current = {
          values: aiStatement(values),
          comment: comment.trim(),
          ...(initial.version
            ? { id: initial.version.id, etag: rowIfMatch(initial.version.row_version) }
            : {}),
        };
      }
      setBusy(true);
      setRetry(true);
      const attempt = intent.current;
      if (!attempt.id) {
        const created = await command<AISettingsVersion>("POST", AI_SETTINGS_VERSIONS_PATH, {
          values: attempt.values,
        });
        attempt.id = created.id;
        attempt.etag = rowIfMatch(created.row_version);
      }
      const path = `${AI_SETTINGS_VERSIONS_PATH}/${encodeURIComponent(attempt.id)}`;
      const response = await send("GET", path);
      if (!response.ok) throw await readProblem(response);
      const version = (await response.json()) as AISettingsVersion;
      if (version.status !== "SUBMITTED") {
        if (version.status !== "DRAFT" && version.status !== "TESTED")
          throw new Error(label("changed"));
        if (!attempt.job) {
          if (!attempt.etag) throw new Error(label("missingVersion"));
          await command<AISettingsVersion>(
            "PATCH",
            path,
            { values: attempt.values, unset: [] },
            attempt.etag,
          );
          attempt.job = (
            await command<{ id: string }>("POST", `${path}/test`, { run_simulation: true })
          ).id;
        }
        let job = await fetchJob(attempt.job);
        for (let poll = 0; poll < 30 && !isTerminal(job); poll++) {
          await new Promise((resolve) => setTimeout(resolve, 2000));
          job = await fetchJob(attempt.job);
        }
        if (!isTerminal(job)) throw new Error(label("stillTesting"));
        if (job.state !== "SUCCEEDED") {
          throw new Error(job.problem?.detail ?? label("testFailed"));
        }
      }
      // Replay our own submission even when the read says SUBMITTED. Another user's
      // submission must not be mistaken for success of this intent.
      await command<AISettingsVersion>("POST", `${path}/submit`, { comment: attempt.comment });
      intent.current = null;
      keys.clear();
      setRetry(false);
      toast.show({ tone: "positive", message: label("submitted") });
      await refresh();
    } catch (e) {
      refused(e);
    } finally {
      setBusy(false);
    }
  }
  async function disable() {
    if (disabling) return;
    setDisabling(true);
    setError(null);
    setProblem(null);
    try {
      const response = await disableKeys.send("POST", "/api/v1/tenant/ai/disable", {
        body: { comment: disableComment.trim() || null },
      });
      if (!response.ok) throw await readProblem(response);
      setConfirm(false);
      toast.show({ tone: "positive", message: label("disabledToast") });
      await refresh();
    } catch (e) {
      refused(e);
    } finally {
      setDisabling(false);
    }
  }
  return (
    <>
      <section
        aria-label={label("assistance")}
        data-testid="SF-15-ai-status"
        className="flex flex-col gap-3"
      >
        <h2 className="text-title-sm">
          {label("assistance")}: {label(initial.status.enabled ? "on" : "off")}
        </h2>
        <p>
          {label("provider")}: {initial.status.provider} · {label("model")}: {initial.status.model}{" "}
          · {label("budget")}: {initial.status.monthly_token_budget}
        </p>
        {!initial.status.enabled && <p>{label("offHelp")}</p>}
        {initial.status.platform_disabled && <Banner tone="warning" title={label("platformOff")} />}
        <div className="flex justify-end">
          <Button
            variant="danger"
            disabledReason={disabling ? label("busy") : undefined}
            onClick={() => setConfirm(true)}
          >
            {label("disable")}
          </Button>
        </div>
      </section>
      {error && <Banner tone="negative" title={error} />}
      <RefusalBanner problem={problem} />
      {submitted ? (
        <div data-testid="SF-15-banner-ai-pending">
          <Banner
            tone="info"
            announce="live"
            title={
              initial.approval
                ? t(PREFIX + "pendingDetails", {
                    request: initial.approval.request_no,
                    name: initial.approval.preparer.display_name,
                  })
                : label("pending")
            }
            actions={
              requestId ? (
                <Link to={requestRoute(requestId)}>{label("viewRequest")}</Link>
              ) : undefined
            }
          />
        </div>
      ) : (
        <form
          aria-label={label("change")}
          data-testid="SF-15-ai-form"
          onSubmit={(e) => {
            e.preventDefault();
            void submit();
          }}
          className="flex flex-col gap-4"
        >
          <h2 className="text-title-sm">{label("change")}</h2>
          {initial.version && (
            <p>
              {label("resume")}: {initial.version.version_no}
            </p>
          )}
          <fieldset disabled={busy || retry} className="flex flex-col gap-4">
            {FIELDS.map(([code, key, kind]) =>
              kind === "boolean" && key !== "enabled" ? (
                <label key={code} className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    checked={values[code] === true}
                    onChange={(e) => setValues((v) => ({ ...v, [code]: e.target.checked }))}
                  />
                  {label(key)}
                </label>
              ) : kind === "boolean" ? (
                <fieldset key={code} className="flex gap-3">
                  <legend>{label(key)}</legend>
                  {[true, false].map((value) => (
                    <label key={String(value)}>
                      <input
                        type="radio"
                        name={code}
                        checked={values[code] === value}
                        onChange={() => setValues((v) => ({ ...v, [code]: value }))}
                      />{" "}
                      {label(value ? "on" : "off")}
                    </label>
                  ))}
                </fieldset>
              ) : (
                <Field
                  key={code}
                  name={code}
                  label={label(key)}
                  required
                  help={kind === "percent" ? label("percent") : undefined}
                >
                  {(control) => (
                    <input
                      {...control}
                      className={controlClass(false)}
                      value={String(values[code] ?? "")}
                      inputMode={kind === "text" ? "text" : "decimal"}
                      onChange={(e) => setValues((v) => ({ ...v, [code]: e.target.value }))}
                    />
                  )}
                </Field>
              ),
            )}
            <ReasonField
              name="comment"
              label={label("comment")}
              value={comment}
              onChange={setComment}
            />
          </fieldset>
          {retry && <p>{label("retryHelp")}</p>}
          <div className="flex justify-end">
            <Button type="submit" variant="primary" loading={busy}>
              {label(retry ? "retry" : "submit")}
            </Button>
          </div>
        </form>
      )}
      <Modal
        open={confirm}
        variant="confirmation"
        title={label("disableTitle")}
        description={label("disableHelp")}
        submitting={disabling}
        onClose={() => setConfirm(false)}
        primaryAction={{
          label: label("disable"),
          destructive: true,
          onAction: () => void disable(),
        }}
      >
        <Field name="disable-comment" label={label("comment")} optional>
          {(control) => (
            <textarea
              {...control}
              className={controlClass(false, true)}
              value={disableComment}
              onChange={(e) => setDisableComment(e.target.value)}
            />
          )}
        </Field>
        <RefusalBanner problem={problem} />
      </Modal>
    </>
  );
}
