// Report runs as the pass asks for them and reads them (release candidate QA; PROGRESS.md D-99 (7)):
// a JSON run with stated parameters, the built-in tie-outs it states (04 table 10-T), and the
// subledger's revenue of a period as the cockpit's journal preview totals it by account role.
import { type Api, at, cents, decimal, items, said, text } from "./api";
import { flat } from "./record";

export interface Run {
  /** The run's id, or "" when the request was refused. */
  readonly id: string;
  /** What the request and the job answered, for the record. */
  readonly said: string;
  /** The run as `GET /report-runs/{id}` states it once its job ended; null when refused. */
  readonly run: unknown;
}

/** A JSON report run with the parameters given, and the run as the API states it once it ended. */
export async function makeRun(
  api: Api,
  code: string,
  parameters: Record<string, unknown>,
): Promise<Run> {
  const started = await api.send("POST", "/api/v1/report-runs", {
    report_code: code,
    parameters,
    output_format: "JSON",
  });
  if (started.status !== 202) {
    // A refusal names its members: the sentences of the first two are the answer to the request.
    const errors = items(started.json, "errors")
      .slice(0, 2)
      .map((error) => `${text(error, "field")}: ${text(error, "message")}`);
    return {
      id: "",
      said: `${said(started)} ${flat(text(started.json, "detail"), 160)}${errors.length === 0 ? "" : ` [${flat(errors.join(" | "), 420)}]`}`.trim(),
      run: null,
    };
  }
  const id = started.headers["x-erev-report-run-id"] ?? "";
  const state = await api.job(started);
  const run = (await api.get(`/api/v1/report-runs/${id}`)).json;
  return {
    id,
    said: `run ${text(run, "report_run_no")} ${text(run, "status")} (job ${state})`,
    run,
  };
}

/** The decimal string of an API-S-Money value, or "". */
export function money(value: unknown): string {
  return text(value, "amount");
}

/** The tie-outs of a run, each as "CODE RESULT (expected …; actual …)", and those that failed. */
export function tieOuts(run: unknown): { readonly lines: string[]; readonly failed: string[] } {
  const lines: string[] = [];
  const failed: string[] = [];
  for (const result of items(run, "tie_out_results")) {
    const amounts = (side: string) =>
      items(result, side)
        .map((item) => `${text(item, "currency")} ${money(item)}`)
        .join(", ");
    const line = `${text(result, "code")} ${text(result, "result")}${text(result, "result") === "NOT_APPLICABLE" ? "" : ` (expected ${amounts("expected")}; actual ${amounts("actual")})`}`;
    lines.push(line);
    if (text(result, "result") === "FAIL") {
      failed.push(line);
    }
  }
  return { lines, failed };
}

/** Credit less debit of the REVENUE role in a period's subledger (04 API-S-PeriodCockpit). */
export async function subledgerRevenue(api: Api, periodId: string): Promise<string> {
  const cockpit = (await api.get(`/api/v1/periods/${periodId}/cockpit`)).json;
  const role = items(cockpit, "journal_preview", "by_account_role").find(
    (item) => text(item, "account_role") === "REVENUE",
  );
  const credit = cents(money(at(role, "credit")));
  const debit = cents(money(at(role, "debit")));
  return credit === null || debit === null ? "" : decimal(credit - debit);
}

export interface JournalRevenue {
  /** Credit less debit of the REVENUE role over the runs that are not cancelled, or "". */
  readonly total: string;
  /** One line per run: its number, state, grain, line count and REVENUE amount. */
  readonly runs: readonly string[];
}

/**
 * The REVENUE role in the journals of a period: the journal lines of every run that is not
 * cancelled, credit less debit in functional currency (04 API-S-JournalLine). It is the figure the
 * ledger receives, read line by line, to set beside the subledger's.
 */
export async function journalRevenue(
  api: Api,
  entity: string,
  book: string,
  periodKey: string,
): Promise<JournalRevenue> {
  const runs = await api.list("/api/v1/journal-runs", { entity, book, period: periodKey });
  let total = 0n;
  let read = true;
  const lines: string[] = [];
  for (const run of runs) {
    const state = text(run, "state");
    const name = `${text(run, "run_no")} ${state}, ${text(run, "mode")} ${text(run, "grain")}, ${text(run, "totals", "line_count")} lines`;
    if (state === "cancelled") {
      lines.push(`${name}: not counted`);
      continue;
    }
    let revenue = 0n;
    for (const line of await api.list(`/api/v1/journal-runs/${text(run, "id")}/lines`, {
      account_role: "REVENUE",
    })) {
      const credit = cents(money(at(line, "credit_functional")));
      const debit = cents(money(at(line, "debit_functional")));
      if (credit === null || debit === null) {
        read = false;
      } else {
        revenue += credit - debit;
      }
    }
    total += revenue;
    lines.push(`${name}: REVENUE ${decimal(revenue)}`);
  }
  return { total: read ? decimal(total) : "", runs: lines };
}
