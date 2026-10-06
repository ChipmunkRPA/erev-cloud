// Section E of the pass: the figures of the closed periods (PRD WLD-P-02: AVM-US, ASC 606, January
// to August 2026, each locked through a close run). One fact is read from every place that states
// it — the recognized revenue of a month from the revenue waterfall, from the subledger by account
// role (the cockpit's journal preview) and from Home's key figure; a closing balance from the
// roll-forward and from the balances report — and the places must agree to the cent (PRD J-13-AC-3
// "journal totals by account equal waterfall activity", CTL-019; 04 table 10-T, the built-in
// tie-outs). A figure on a screen is read through its Explain trigger's name, which states it with
// its currency, and compared with the API member the screen shows.
import type { Page } from "@playwright/test";

import { Api, at, cents, decimal, grouped, items, text } from "../api";
import type { Qa } from "../fixtures";
import { failuresText, look, open } from "../observe";
import { flat, type Outcome } from "../record";
import { normaliseKey } from "../../screens";
import { makeRun, money, type Run, subledgerRevenue, tieOuts } from "../reports";
import { figures, scrolledRow } from "../steps";
import { AUGUST, BOOK, CLOSED_KEYS, reportRows, SEPTEMBER } from "../world";

const ENTITY = "AVM-US";
const CONTEXT = `entity=${ENTITY}&period=${AUGUST}&book=${BOOK}`;
/** Register index 264: the as-locked default of the views over a closed period. */
const AS_LOCKED = "264";

interface Month {
  readonly key: string;
  readonly state: string;
  readonly waterfall: string;
  readonly subledger: string;
  readonly home: string;
}

async function readMonths(
  api: Api,
): Promise<{ readonly months: Month[]; readonly run: Run; readonly rows: readonly unknown[] }> {
  const periods = await api.list("/api/v1/periods", { entity: ENTITY, book: BOOK });
  const run = await makeRun(api, "revenue_waterfall", {
    entity_codes: [ENTITY],
    book: BOOK,
    from_period_key: CLOSED_KEYS[0],
    to_period_key: CLOSED_KEYS.at(-1),
  });
  const rows = run.id === "" ? [] : await reportRows(api, run.id);
  const total = rows.find((row) => text(row, "row_key").startsWith("TOTAL:"));
  const months: Month[] = [];
  for (const key of CLOSED_KEYS) {
    const period = periods.find((item) => text(item, "period", "period_key") === key);
    const home = (
      await api.get("/api/v1/dashboard/home", { entity: ENTITY, period: key, book: BOOK })
    ).json;
    months.push({
      key,
      state: text(period, "state"),
      waterfall: money(at(total, `period:${key}`)),
      subledger: period === undefined ? "" : await subledgerRevenue(api, text(period, "id")),
      home: money(at(home, "revenue", "current")),
    });
  }
  return { months, run, rows };
}

function monthsText(months: readonly Month[]): string {
  return months
    .map(
      (month) =>
        `${month.key} (${month.state}): waterfall ${month.waterfall}, subledger ${month.subledger}, Home ${month.home}`,
    )
    .join("; ");
}

function disagreeing(months: readonly Month[]): readonly Month[] {
  return months.filter(
    (month) =>
      month.waterfall === "" ||
      cents(month.waterfall) !== cents(month.subledger) ||
      cents(month.waterfall) !== cents(month.home),
  );
}

async function revenueTie(api: Api): Promise<Outcome> {
  let read = await readMonths(api);
  const open2 = read.months.filter(
    (month) => month.state !== "closed" && month.state !== "permanently_locked",
  );
  if (open2.length > 0) {
    return {
      observed: `the world was seeded without the close: ${open2.map((month) => `${month.key} is ${month.state}`).join(", ")} (PRD WLD-P-02 rev 1.162 asks for a seed with the close). ${monthsText(read.months)}`,
      result: "not run",
    };
  }
  let off = disagreeing(read.months);
  if (off.length > 0) {
    // A candidate: every place is read a second time before it is written.
    const again = await readMonths(api);
    const still = disagreeing(again.months).filter((month) =>
      off.some((first) => first.key === month.key),
    );
    if (still.length === 0) {
      return {
        observed: `a difference at the first reading (${monthsText(off)}) was not there at the second. ${monthsText(again.months)}`,
        result: "seen once",
      };
    }
    read = again;
    off = still;
  }
  const ties = tieOuts(read.run.run);
  // The rows of the report add to its total line.
  const sums: string[] = [];
  for (const key of CLOSED_KEYS) {
    let sum = 0n;
    for (const row of read.rows) {
      if (!text(row, "row_key").startsWith("TOTAL:")) {
        sum += cents(money(at(row, `period:${key}`))) ?? 0n;
      }
    }
    const total = read.months.find((month) => month.key === key)?.waterfall ?? "";
    if (cents(total) !== sum) {
      sums.push(`${key}: the rows add to ${decimal(sum)}, the total line says ${total}`);
    }
  }
  const totals = read.rows
    .map((row) => text(row, "row_key"))
    .filter((key) => key.startsWith("TOTAL:"));
  const summary = `${read.run.said}, ${String(read.rows.length)} rows, total line(s) [${totals.join(", ")}]; ${monthsText(read.months)}; tie-outs: ${ties.lines.join("; ") || "none stated"}`;
  if (off.length > 0 || ties.failed.length > 0 || sums.length > 0) {
    return {
      observed: `${[off.length > 0 ? `THE PLACES DISAGREE, twice: ${monthsText(off)}` : "", ties.failed.length > 0 ? `TIE-OUT FAILED: ${ties.failed.join("; ")}` : "", sums.length > 0 ? `ROWS DO NOT ADD: ${sums.join("; ")}` : ""].filter((part) => part !== "").join(". ")}. ${summary}`,
      result: "FINDING",
      finding: "wrong figure",
    };
  }
  return { observed: summary, result: "pass" };
}

/** The balance reports of the closed months: each built-in tie-out, and closing against closing. */
async function balanceTies(api: Api): Promise<Outcome> {
  const range = {
    entity_codes: [ENTITY],
    book: BOOK,
    from_period_key: CLOSED_KEYS[0],
    to_period_key: AUGUST,
  };
  const at8 = { entity_codes: [ENTITY], book: BOOK, period_key: AUGUST };
  const lines: string[] = [];
  const failed: string[] = [];
  const unread: string[] = [];
  const unasked: string[] = [];
  for (const [code, parameters] of [
    ["contract_balance_rollforward", range],
    ["contract_balances", at8],
    ["rpo_rollforward", range],
    ["rpo", at8],
    ["disaggregation", range],
  ] as const) {
    let run = await makeRun(api, code, parameters);
    let ties = tieOuts(run.run);
    if (ties.failed.length > 0) {
      run = await makeRun(api, code, parameters);
      ties = tieOuts(run.run);
    }
    if (run.id === "") {
      // The request itself was refused: the parameters of the pass, not a run of the product.
      unasked.push(`${code}: ${run.said}`);
    } else if (text(run.run, "status") !== "SUCCEEDED") {
      unread.push(`${code}: ${run.said} ${flat(text(run.run, "problem", "detail"), 200)}`);
    }
    failed.push(...ties.failed.map((line) => `${code}: ${line}`));
    lines.push(`${code}: ${run.said}; ${ties.lines.join("; ") || "no tie-out stated"}`);
  }
  if (failed.length > 0) {
    return {
      observed: `TIE-OUT FAILED, twice: ${failed.join(" | ")}. ${lines.join(" || ")}`,
      result: "FINDING",
      finding: "wrong figure",
    };
  }
  if (unread.length > 0) {
    return {
      observed: `a report did not run: ${unread.join(" | ")}. ${lines.join(" || ")}`,
      result: "FINDING",
      finding: "stopped flow",
    };
  }
  if (unasked.length > 0) {
    return {
      observed: `a run was refused as the pass asked for it: ${unasked.join(" | ")}. ${lines.join(" || ")}`,
      result: "seen once",
    };
  }
  return { observed: lines.join(" || "), result: "pass" };
}

interface Rollforward {
  /** The run in words: its lock, its opening, other and closing lines, its tie-outs. */
  readonly said: string;
  /** Contract asset and contract liability of the OPENING and of the CLOSING line; "" when unread. */
  readonly opening: string;
  readonly closing: string;
  readonly failed: readonly string[];
}

/** One run of the contract balance roll-forward, read by its line rows (row key `<LINE>[:<currency>]`). */
async function rollforward(
  api: Api,
  label: string,
  parameters: Record<string, unknown>,
): Promise<Rollforward> {
  const run = await makeRun(api, "contract_balance_rollforward", parameters);
  if (run.id === "") {
    return { said: `${label}: ${run.said}`, opening: "", closing: "", failed: [] };
  }
  const rows = await reportRows(api, run.id);
  // A current run states API-S-Money; an as-locked run renders the frozen cells as text.
  const cell = (row: unknown, member: string) =>
    money(at(row, member)) || text(row, member) || "none stated";
  const of = (key: string) => rows.filter((item) => text(item, "row_key").split(":")[0] === key);
  const line = (key: string) => {
    const found = of(key);
    return found.length === 0
      ? `${key} not among the rows`
      : found
          .map(
            (row) =>
              `${text(row, "row_key")} asset ${cell(row, "contract_asset")}, liability ${cell(row, "contract_liability")}`,
          )
          .join(" / ");
  };
  const pair = (key: string) =>
    of(key)
      .map((row) => `${cell(row, "contract_asset")}|${cell(row, "contract_liability")}`)
      .join("/");
  const ties = tieOuts(run.run);
  const tieSaid =
    ties.lines.length === 0
      ? "no tie-out stated"
      : ties.failed.length > 0
        ? ties.lines.join("; ")
        : ties.lines.map((item) => item.split(" ").slice(0, 2).join(" ")).join(", ");
  const keys =
    of("OPENING").length + of("CLOSING").length > 0
      ? ""
      : `; the run's row keys [${rows
          .slice(0, 8)
          .map((row) => text(row, "row_key"))
          .join(", ")}]`;
  return {
    said: `${label}: ${run.said}, lock ${text(run.run, "period_lock_id").slice(0, 8) || "none"}; ${line("OPENING")}; ${line("OTHER")}; ${line("CLOSING")}; ${tieSaid}${keys}`,
    opening: pair("OPENING"),
    closing: pair("CLOSING"),
    failed: ties.failed.map((item) => `${label}: ${item}`),
  };
}

/** Two amounts "asset|liability" as one figure each, compared to the cent where both are decimals. */
function sameBalances(left: string, right: string): boolean {
  // A frozen cell is text and may carry its currency code or grouped digits; a current one is a
  // plain decimal.
  const parts = (value: string) =>
    value.split(/[|/]/).map((part) => cents(part.replace(/^[A-Z]{3}\s+/, "").replace(/,/g, "")));
  const one = parts(left);
  const other = parts(right);
  return one.some((part) => part === null) || other.some((part) => part === null)
    ? left === right
    : one.length === other.length && one.every((part, index) => part === other[index]);
}

/** The lock a run names for a period: the one whose datasets stand, else the current record. */
function lockOf(period: unknown): { readonly id: string; readonly said: string } {
  // 04 API-S-Period `dataset_lock` (register index 280): a run that names a record which froze
  // nothing is refused where it is created. A read without the member names the current record.
  const standing = text(period, "dataset_lock", "id");
  return standing === ""
    ? {
        id: text(period, "current_lock", "id"),
        said: `current_lock ${text(period, "current_lock", "kind") || "of no stated kind"}`,
      }
    : { id: standing, said: `dataset_lock ${text(period, "dataset_lock", "kind")}` };
}

/** What the measurements of the roll-forward hand from one row to the next. */
interface LockedChain {
  /** The CLOSING line of August as its lock froze it; "" when unread. */
  augustClosing: string;
}

/**
 * Measured for register index 297 (RPT-ROLLFWD-LOCKED-CLOSING-1; the supervisor's word of
 * 2026-10-02 on row E-2): the roll-forward as each lock froze it. A run that names a lock is of the
 * lock's own period (ENGINE_SPEC_B S15-R-19: every period selector must equal the lock's), so the
 * range of E-2 as locked is the chain of the months' own datasets: each is read, and each month must
 * open on the closing of the month before. The row states what each run says; the finding is E-2's.
 */
async function lockedRollforwards(api: Api, chain: LockedChain): Promise<Outcome> {
  const periods = await api.list("/api/v1/periods", { entity: ENTITY, book: BOOK });
  const base = { entity_codes: [ENTITY], book: BOOK };
  const months = [...CLOSED_KEYS, SEPTEMBER];
  const lines: string[] = [];
  const failed: string[] = [];
  const breaks: string[] = [];
  let before: { readonly key: string; readonly closing: string } | null = null;
  for (const key of months) {
    const period = periods.find((item) => text(item, "period", "period_key") === key);
    const lock = lockOf(period);
    if (lock.id === "") {
      lines.push(`${key} (${text(period, "state") || "not listed"}) names no lock`);
      before = null;
      continue;
    }
    const run = await rollforward(api, `${key} as locked (${lock.said})`, {
      ...base,
      period_lock_id: lock.id,
    });
    lines.push(run.said);
    failed.push(...run.failed);
    if (before !== null && before.closing !== "" && run.opening !== "") {
      if (!sameBalances(before.closing, run.opening)) {
        breaks.push(
          `${key} opens on asset|liability ${run.opening}; ${before.key} closes on ${before.closing}`,
        );
      }
    }
    before = { key, closing: run.closing };
    if (key === AUGUST) {
      chain.augustClosing = run.closing;
    }
  }
  const body = lines.join(" || ");
  if (failed.length > 0 || breaks.length > 0) {
    return {
      observed: `${[failed.length > 0 ? `a tie-out of an as-locked run fails: ${failed.join(" | ")}` : "", breaks.length > 0 ? `a month does not open on the closing of the month before: ${breaks.join(" | ")}` : ""].filter((part) => part !== "").join(". ")} (the finding is row E-2's). ${body}`,
      result: "seen once",
    };
  }
  return {
    observed: `each locked month opens on the closing of the month before. ${body}`,
    result: "pass",
  };
}

/**
 * Measured for register index 297, the other half: the range of E-2 asked as locked — the answer
 * the product gives a run that names a lock and another period — and the roll-forward of September
 * alone in current figures, against the closing August's lock froze.
 */
async function septemberRollforward(api: Api, chain: LockedChain): Promise<Outcome> {
  const periods = await api.list("/api/v1/periods", { entity: ENTITY, book: BOOK });
  const august = periods.find((period) => text(period, "period", "period_key") === AUGUST);
  const base = { entity_codes: [ENTITY], book: BOOK };
  const lock = lockOf(august);
  const lines: string[] = [];
  if (lock.id === "") {
    lines.push(`${AUGUST} names no lock: the range was not asked as locked`);
  } else {
    const ranged = await rollforward(
      api,
      `${CLOSED_KEYS[0] ?? ""} to ${AUGUST} with the lock of ${AUGUST} (${lock.said})`,
      { ...base, period_lock_id: lock.id, from_period_key: CLOSED_KEYS[0], to_period_key: AUGUST },
    );
    lines.push(ranged.said);
  }
  const september = await rollforward(api, `${SEPTEMBER} alone, current figures`, {
    ...base,
    from_period_key: SEPTEMBER,
    to_period_key: SEPTEMBER,
  });
  lines.push(september.said);
  const opens =
    chain.augustClosing === "" || september.opening === ""
      ? `the opening of ${SEPTEMBER} was not set beside the locked closing of ${AUGUST} (one of them is unread)`
      : sameBalances(chain.augustClosing, september.opening)
        ? `${SEPTEMBER} opens on the closing ${AUGUST}'s lock froze (asset|liability ${september.opening})`
        : `${SEPTEMBER} OPENS ON asset|liability ${september.opening}; ${AUGUST}'s lock froze the closing ${chain.augustClosing}`;
  const off = september.failed.length > 0 || opens.includes("OPENS ON");
  return {
    observed: `${opens}${september.failed.length === 0 ? "" : `; a tie-out fails: ${september.failed.join(" | ")}`}${off ? " (the finding is row E-2's)" : ""}. ${lines.join(" || ")}`,
    result: off ? "seen once" : "pass",
  };
}

/** The journals of the closed months: every run acknowledged and balanced. */
async function journalTies(api: Api): Promise<Outcome> {
  const lines: string[] = [];
  const wrong: string[] = [];
  for (const key of CLOSED_KEYS) {
    const runs = (
      await api.list("/api/v1/journal-runs", { entity: ENTITY, book: BOOK, period: key })
    ).filter((run) => text(run, "state") !== "cancelled");
    if (runs.length === 0) {
      wrong.push(`${key}: no journal run`);
      continue;
    }
    for (const run of runs) {
      const debit = money(at(run, "totals", "debit_functional"));
      const credit = money(at(run, "totals", "credit_functional"));
      const summary = (await api.get(`/api/v1/journal-runs/${text(run, "id")}/summary`)).json;
      const differences = items(summary, "balance_checks").map((check) =>
        money(at(check, "difference")),
      );
      lines.push(
        `${key} ${text(run, "run_no")} ${text(run, "state")}: Dr ${debit} Cr ${credit}, ${String(differences.length)} balance check(s)`,
      );
      if (
        cents(debit) !== cents(credit) ||
        at(run, "totals", "balanced") !== true ||
        differences.some((difference) => cents(difference) !== 0n)
      ) {
        wrong.push(
          `${key} ${text(run, "run_no")}: Dr ${debit}, Cr ${credit}, differences [${differences.join(", ")}]`,
        );
      }
      if (text(run, "state") !== "acknowledged") {
        wrong.push(`${key} ${text(run, "run_no")} is ${text(run, "state")} in a closed month`);
      }
    }
  }
  return wrong.length === 0
    ? { observed: lines.join("; "), result: "pass" }
    : {
        observed: `${wrong.join(" | ")}. ${lines.join("; ")}`,
        result: "FINDING",
        finding: "wrong figure",
      };
}

/** The report view of a closed month on screen: what it says it shows, and three rows against the run. */
async function waterfallScreen(page: Page, api: Api): Promise<Outcome> {
  const address = `/reports/revenue_waterfall?${CONTEXT}`;
  await page.goto(address);
  await page.waitForURL(/[?&]run=[0-9a-f-]{36}(&|$)/, { timeout: 60_000 }).catch(() => undefined);
  const stamp = page.getByTestId("SF-08-run-stamp");
  await stamp.waitFor({ state: "visible", timeout: 60_000 }).catch(() => undefined);
  const seen = await look(page, address);
  const runId = new URL(page.url()).searchParams.get("run") ?? "";
  const stampText = flat(await stamp.innerText({ timeout: 2_000 }).catch(() => ""), 200);
  const strip = flat(
    await page
      .getByTestId("SF-08-banner-tie-outs")
      .getByRole("heading")
      .first()
      .innerText({ timeout: 2_000 })
      .catch(() => ""),
    80,
  );
  const said2 = (
    await page
      .getByRole("alert")
      .allInnerTexts()
      .catch(() => [] as string[])
  ).map((item) => flat(item, 160));
  const lockLine = flat(
    await page
      .getByText(/^Showing (current figures|.+ as locked)/)
      .first()
      .innerText({ timeout: 2_000 })
      .catch(() => ""),
    200,
  );
  const lead = `the view is ${seen.state} ("${seen.heading}"); stamp "${stampText}"; ${lockLine === "" ? "no as-locked line" : `"${lockLine}"`}; ${strip === "" ? "no tie-out strip" : strip}; alerts [${said2.join(" | ")}]; refused requests: ${failuresText(seen)}`;
  if (runId === "") {
    // Index 264 describes views of a closed month whose as-locked request is refused. A view that
    // makes no run for another reason is not that item: it is read by hand.
    const refused = seen.answers.some(
      (answer) =>
        answer.method === "POST" &&
        answer.path.startsWith("/api/v1/report-runs") &&
        answer.status === 422,
    );
    return refused
      ? {
          observed: `no run was made: the view's own request was refused with 422. ${lead}`,
          result: "KNOWN",
          known: AS_LOCKED,
          page,
        }
      : {
          observed: `no run was made, and no request of the view was refused with 422. ${lead}`,
          result: "seen once",
          page,
        };
  }
  // The run is a job: its rows are read once it has ended.
  let run = (await api.get(`/api/v1/report-runs/${runId}`)).json;
  for (let turn = 0; turn < 90 && /^(QUEUED|RUNNING|)$/.test(text(run, "status")); turn += 1) {
    await new Promise((resolve) => setTimeout(resolve, 1_000));
    run = (await api.get(`/api/v1/report-runs/${runId}`)).json;
  }
  const rows = (await reportRows(api, runId)).filter(
    (row) => !text(row, "row_key").startsWith("TOTAL:"),
  );
  const grid = page
    .getByTestId("SF-08-grid-revenue-waterfall")
    .getByRole("grid", { name: "Revenue waterfall" });
  await grid.waitFor({ state: "visible", timeout: 30_000 }).catch(() => undefined);
  const picked = [rows[0], rows[Math.floor(rows.length / 2)], rows.at(-1)].filter(
    (row) => row !== undefined,
  );
  const asLocked = text(run, "period_lock_id") !== "";
  const compared: string[] = [];
  const wrong: string[] = [];
  /** Frozen decimals the pass did not find in their row on the screen: read by hand. */
  const unmatched: string[] = [];
  let read = 0;
  for (const row of picked) {
    // The grid names a row by its key without the kind prefix (viewer/specs.ts `rowTestKey`).
    const rowKey = text(row, "row_key");
    const colon = rowKey.indexOf(":");
    const key = colon < 0 ? rowKey : rowKey.slice(colon + 1);
    const shown = await scrolledRow(page, grid, `SF-08-row-${normaliseKey(key)}`);
    if (shown === null) {
      compared.push(`${key}: the row is not in the grid`);
      continue;
    }
    if (asLocked) {
      // A frozen row is text in every cell and no figure of it is explained (ENGINE_SPEC_B
      // S15-R-19): its decimal cells are looked for in the row as the grid shows it.
      const cells = (
        await shown
          .getByRole("gridcell")
          .allInnerTexts()
          .catch(() => [] as string[])
      )
        .map((cell) => flat(cell, 40))
        .filter((cell) => cell !== "");
      const shownText = cells.join(" | ");
      const decimals = Object.entries(
        typeof row === "object" && row !== null ? (row as Record<string, unknown>) : {},
      ).filter(
        (entry): entry is [string, string] =>
          typeof entry[1] === "string" && /^-?\d+\.\d{2}$/.test(entry[1]),
      );
      const missing = decimals.filter(
        ([, value]) => !shownText.includes(value) && !shownText.includes(grouped(value)),
      );
      compared.push(
        `${key}: the frozen row states ${decimals.map(([name, value]) => `${name} ${value}`).join(", ") || "no decimal cell"}; the screen's row reads [${cells.slice(0, 12).join(" | ")}]`,
      );
      if (missing.length > 0) {
        unmatched.push(`${key}: ${missing.map(([name, value]) => `${name} ${value}`).join(", ")}`);
      } else if (decimals.length > 0) {
        read += 1;
      }
      continue;
    }
    const amount = money(at(row, `period:${AUGUST}`));
    const figure = (await figures(shown)).find((item) => item.label.startsWith("Aug 2026"));
    const expected = `${text(at(row, `period:${AUGUST}`), "currency")} ${grouped(amount)}`;
    compared.push(`${key}: screen "${figure?.value ?? "no figure"}", API ${expected}`);
    if (figure !== undefined && figure.value !== expected) {
      wrong.push(`${key}: the screen says ${figure.value}, the run's row says ${expected}`);
    } else if (figure !== undefined) {
      read += 1;
    }
  }
  const ties = tieOuts(run);
  const observed = `${lead}; the run ${text(run, "report_run_no")} is ${text(run, "status")} and names lock ${text(run, "period_lock_id") || "none"}; ${String(rows.length)} rows; ${compared.join("; ")}; tie-outs of the run: ${ties.lines.join("; ") || "none stated"}`;
  if (wrong.length > 0) {
    return {
      observed: `A FIGURE DIFFERS FROM THE MEMBER IT SHOWS: ${wrong.join(" | ")}. ${observed}`,
      result: "FINDING",
      finding: "wrong figure",
      page,
    };
  }
  const saysLocked = /as locked/i.test(`${stampText} ${lockLine}`);
  const ofLock = text(run, "period_lock_id") !== "";
  if (saysLocked && !ofLock) {
    // "As locked" over a run that names no lock is register index 264's ground: marked, not
    // reported again.
    return {
      observed: `the view says "as locked" over a run that names no lock. ${observed}`,
      result: "KNOWN",
      known: AS_LOCKED,
      page,
    };
  }
  if (!saysLocked && ofLock) {
    return {
      observed: `the run names a lock and the view does not say "as locked". ${observed}`,
      result: "seen once",
      page,
    };
  }
  if (unmatched.length > 0) {
    return {
      observed: `a frozen figure was not found in its row on the screen (read by hand): ${unmatched.join(" | ")}. ${observed}`,
      result: "seen once",
      page,
    };
  }
  if (read === 0) {
    // What the view says of its source was read; no figure of a row was set beside the run's.
    return {
      observed: `no figure of the ${String(picked.length)} rows was read on the screen. ${observed}`,
      result: "seen once",
      page,
    };
  }
  return seen.state === "rendered"
    ? { observed, result: "pass", page }
    : { observed, result: "seen once", page };
}

/** Home's key figures of a closed month on screen against the API members they show. */
async function homeScreen(page: Page, api: Api): Promise<Outcome> {
  const address = `/home?${CONTEXT}`;
  const home = (
    await api.get("/api/v1/dashboard/home", { entity: ENTITY, period: AUGUST, book: BOOK })
  ).json;
  const seen = await open(page, address);
  const cell = async (id: string) =>
    flat(
      await page
        .getByTestId(id)
        .first()
        .innerText({ timeout: 5_000 })
        .catch(() => ""),
      80,
    );
  const pairs = [
    ["Revenue", await cell("SF-01-kpi-revenue"), grouped(money(at(home, "revenue", "current")))],
    [
      "Contract liability",
      await cell("SF-01-kpi-contract-liability"),
      grouped(money(at(home, "contract_liability", "closing"))),
    ],
    ["RPO", await cell("SF-01-kpi-rpo"), grouped(money(at(home, "rpo", "total")))],
  ] as const;
  const wrong = pairs.filter(([, shown, expected]) => shown !== "" && !shown.includes(expected));
  const observed = `${seen.state} "${seen.heading}"; ${pairs.map(([name, shown, expected]) => `${name}: screen "${shown}", API ${expected}`).join("; ")}; refused requests: ${failuresText(seen)}`;
  if (wrong.length > 0) {
    const again = await open(page, address);
    const still: string[] = [];
    for (const [name, , expected] of wrong) {
      const id =
        name === "Revenue"
          ? "SF-01-kpi-revenue"
          : name === "RPO"
            ? "SF-01-kpi-rpo"
            : "SF-01-kpi-contract-liability";
      const shown = await cell(id);
      if (!shown.includes(expected)) {
        still.push(`${name}: screen "${shown}", API ${expected}`);
      }
    }
    return still.length > 0
      ? {
          observed: `A KEY FIGURE DIFFERS FROM THE MEMBER IT SHOWS, twice: ${still.join(" | ")}. ${observed}`,
          result: "FINDING",
          finding: "wrong figure",
          page,
        }
      : {
          observed: `a difference at the first reading was not there at the second (${again.state}). ${observed}`,
          result: "seen once",
          page,
        };
  }
  return seen.state === "rendered"
    ? { observed, result: "pass", page }
    : { observed, result: "seen once", page };
}

export async function figuresSection({ record, sessions }: Qa): Promise<void> {
  const page = await sessions.page("marcus");
  const api = new Api(page);

  await record.check(
    {
      check: "E-1 recognized revenue of each closed month, three places",
      persona: "marcus",
      address: `revenue_waterfall ${ENTITY} ${CLOSED_KEYS[0] ?? ""} to ${AUGUST}; GET periods/<id>/cockpit; GET dashboard/home`,
      expected:
        "For each of the eight closed months the waterfall's total line, the subledger's REVENUE role (credit less debit) and Home's Revenue key figure state one amount; the rows of the report add to its total line; TO_WATERFALL_EQ_JE_REVENUE passes (PRD J-13-AC-3, CTL-019; 04 table 10-T)",
    },
    () => revenueTie(api),
  );
  await record.check(
    {
      check: "E-2 the balance reports of the closed months",
      persona: "marcus",
      address:
        "contract_balance_rollforward, contract_balances, rpo_rollforward, rpo, disaggregation",
      expected:
        "Each report runs, and each built-in tie-out it states passes: opening plus activity equals closing, the balances equal the roll-forward's closing, the RPO roll-forward closes on the RPO total, the disaggregation totals the revenue journal (04 table 10-T; 03 REQ-RPT-003)",
    },
    () => balanceTies(api),
  );
  const chain: LockedChain = { augustClosing: "" };
  await record.check(
    {
      check: "E-2b the contract balance roll-forward as each lock froze it",
      persona: "marcus",
      address: `contract_balance_rollforward with period_lock_id of each month, ${CLOSED_KEYS[0] ?? ""} to ${SEPTEMBER}`,
      expected:
        "The roll-forward a lock froze foots, and each locked month opens on the closing of the month before (ENGINE_SPEC_B S15-R-19, S15-R-20; supervisor ruling R-72 (b); 04 table 10-T TO_ROLLFORWARD_BALANCES). Measured for register index 297",
    },
    () => lockedRollforwards(api, chain),
  );
  await record.check(
    {
      check: "E-2c the range of E-2 asked as locked, and the roll-forward of September alone",
      persona: "marcus",
      address: `contract_balance_rollforward with period_lock_id of ${AUGUST} and the range of E-2; ${SEPTEMBER} alone`,
      expected: `A run that names a lock is of the lock's own period, so the range is refused by name (ENGINE_SPEC_B S15-R-19); the roll-forward of ${SEPTEMBER} alone opens on the closing ${AUGUST}'s lock froze and foots (S15-R-20; 04 table 10-T). Measured for register index 297`,
    },
    () => septemberRollforward(api, chain),
  );
  await record.check(
    {
      check: "E-3 the journals of the closed months",
      persona: "marcus",
      address: `GET journal-runs?entity=${ENTITY}&period=<each closed month>`,
      expected:
        "Each closed month has its journal run, acknowledged, with debits equal to credits and every balance check at 0.00 (PRD J-13-AC-3 'Each journal batch balances per currency', CTL-022)",
    },
    () => journalTies(api),
  );
  await record.check(
    {
      check: "E-4 the waterfall of a closed month on screen",
      persona: "marcus",
      address: `/reports/revenue_waterfall?${CONTEXT}`,
      expected:
        "The view makes its run and says which reading it shows; a figure of a row is the amount of that row in the run (PRD E2E-02; REQ-UX-005). What it says of the lock is register index 264",
    },
    () => waterfallScreen(page, api),
  );
  await record.check(
    {
      check: "E-5 Home's key figures of a closed month on screen",
      persona: "marcus",
      address: `/home?${CONTEXT}`,
      expected:
        "Revenue, Contract liability and RPO on the screen are the members of GET /dashboard/home for the same context (SCREENS §2.5, §2.6)",
    },
    () => homeScreen(page, api),
  );
}
