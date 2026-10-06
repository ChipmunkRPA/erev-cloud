// What a page of the pass shows (release candidate QA; PROGRESS.md D-99 (7)): the state it settled
// in, its headings, the API answers it asked for with their status and body, and its visible text.
// The settling and the names of the states are the crawl's (support/crawl.ts), so that the two
// projects call one thing by one name.
import type { Page, Response } from "@playwright/test";

import { inspect, notFound, Watch } from "../crawl";

/** The state a settled page is in, as a reader would name it. */
export type PageState =
  | "rendered"
  | "access-limited"
  /** X:not-found, or the not-found state of a record's own screen ("Contract not found"). */
  | "not found"
  | "route error"
  | "sign-in"
  | "did not settle";

/** One API answer of a page: what was asked, the status, and the body when it is JSON. */
export interface Answer {
  readonly method: string;
  /** Pathname and search. */
  readonly path: string;
  readonly status: number;
  /** The body text, cut at `BODY_LIMIT`; empty when it could not be read. */
  readonly body: string;
}

export interface Seen {
  /** The address the pass typed. */
  readonly asked: string;
  /** Pathname and search the page stands on once settled. */
  readonly landed: string;
  readonly state: PageState;
  /** The page's first heading of level 1, or of the state it shows. */
  readonly heading: string;
  /** Every visible heading of levels 1 to 3, in document order. */
  readonly headings: readonly string[];
  /** API answers of 400 and above, requests that failed, uncaught script errors. */
  readonly failures: readonly string[];
  /** Every API answer since the address was typed. */
  readonly answers: readonly Answer[];
  /** The visible text of the document. */
  readonly text: string;
}

const API_PREFIX = "/api/";
const BODY_LIMIT = 2_000_000;
/** "Contract not found", "Period not found", "Page not found": the title of a not-found state. */
const NOT_FOUND = /\bnot found\b/i;

interface Listener {
  readonly watch: Watch;
  readonly answers: Answer[];
  readonly reading: Promise<void>[];
}

/** The bound of one body read, and the margin the watch's own bound is given before it is cut. */
const BODY_MS = 10_000;
const SETTLE_CAP_MS = 50_000;

/** The sign that a wait was cut by `within`, not ended by what it waited for. */
const CUT = Symbol("cut");

/**
 * `work`, or `CUT` when it has not ended in `ms`. A body read is cut because it may never end: while
 * a route of the context intercepts requests (support/network.ts) the browser reports no end for a
 * request whose document was replaced under it (support/crawl.ts says so of its own watch), and the
 * read of such a response's body neither resolves nor rejects. A page that replaces its own
 * document — the sign-out — leaves reads in that state, and a pass that joins them stands still
 * until its test's timeout (the rehearsal of 2026-10-03, round 2, section S).
 */
export async function within<T>(work: Promise<T>, ms: number): Promise<T | typeof CUT> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const cut = new Promise<typeof CUT>((resolve) => {
    timer = setTimeout(() => {
      resolve(CUT);
    }, ms);
  });
  try {
    return await Promise.race([work, cut]);
  } finally {
    clearTimeout(timer);
  }
}

export function wasCut(value: unknown): value is typeof CUT {
  return value === CUT;
}

const LISTENERS = new WeakMap<Page, Listener>();

function listenerOf(page: Page): Listener {
  let listener = LISTENERS.get(page);
  if (listener === undefined) {
    const created: Listener = { watch: new Watch(page), answers: [], reading: [] };
    page.on("response", (response: Response) => {
      const url = new URL(response.url());
      if (!url.pathname.startsWith(API_PREFIX)) {
        return;
      }
      const base = {
        method: response.request().method(),
        path: `${url.pathname}${url.search}`,
        status: response.status(),
      };
      const type = response.headers()["content-type"] ?? "";
      if (!type.includes("json")) {
        created.answers.push({ ...base, body: "" });
        return;
      }
      created.reading.push(
        within(response.text(), BODY_MS).then(
          (body) => {
            created.answers.push({ ...base, body: wasCut(body) ? "" : body.slice(0, BODY_LIMIT) });
          },
          () => {
            created.answers.push({ ...base, body: "" });
          },
        ),
      );
    });
    LISTENERS.set(page, created);
    listener = created;
  }
  return listener;
}

/** Starts the record of a page; call it before the first address is typed. */
export function watchPage(page: Page): void {
  listenerOf(page);
}

/** What the page shows now, once it has settled; the answers and failures since the last call. */
export async function look(page: Page, asked: string): Promise<Seen> {
  const listener = listenerOf(page);
  let settled = true;
  try {
    // The watch's own settling joins the body reads of the refused answers without a bound. Its
    // wait for the page is bounded (45 s): a settling cut beyond that stood in such a join, which
    // the cut call has taken off the watch's list, so a second call settles on the page alone.
    if (wasCut(await within(listener.watch.settle(), SETTLE_CAP_MS))) {
      settled = !wasCut(await within(listener.watch.settle(), SETTLE_CAP_MS));
    }
  } catch {
    settled = false;
  }
  await Promise.all(listener.reading.splice(0));
  const answers = listener.answers.splice(0);
  const { found } = listener.watch.drain([]);
  const url = new URL(page.url());
  const landed = `${url.pathname}${url.search}`;
  const shown = settled ? await inspect(page).catch(() => []) : [];
  const headings = (
    await page
      .locator("h1, h2, h3")
      .evaluateAll((elements) =>
        elements
          .filter((element) => element.checkVisibility())
          .map((element) => (element.textContent ?? "").replace(/\s+/g, " ").trim()),
      )
      .catch(() => [] as string[])
  ).filter((text) => text !== "");
  let state: PageState = "rendered";
  if (!settled) {
    state = "did not settle";
  } else if (url.pathname.startsWith("/sign-in")) {
    state = "sign-in";
  } else if (shown.some((line) => line.startsWith("the route error boundary"))) {
    state = "route error";
  } else if (
    (await notFound(page).count()) > 0 ||
    headings.some((heading) => NOT_FOUND.test(heading))
  ) {
    state = "not found";
  } else if (shown.some((line) => line.startsWith("the no-access state"))) {
    state = "access-limited";
  }
  const heading =
    headings.find((text) => NOT_FOUND.test(text) || text.startsWith("You do not have access")) ??
    (await page
      .getByRole("heading", { level: 1 })
      .first()
      .innerText({ timeout: 2_000 })
      .catch(() => headings[0] ?? ""));
  const text = await page
    .locator("body")
    .innerText({ timeout: 5_000 })
    .catch(() => "");
  return {
    asked,
    landed,
    state,
    heading: heading.replace(/\s+/g, " ").trim(),
    headings,
    failures: found,
    answers,
    text,
  };
}

/** Types an address and says what the page shows. */
export async function open(page: Page, address: string): Promise<Seen> {
  listenerOf(page);
  await page.goto(address).catch(() => undefined);
  return look(page, address);
}

/** A part of a body around a match, for the record. */
function around(text: string, at: number, width = 60): string {
  return text
    .slice(Math.max(0, at - width), at + width)
    .replace(/\s+/g, " ")
    .trim();
}

const WORD_CHARACTER = /[A-Za-z0-9]/;

/**
 * Where `word` stands in `text` as a whole word: not inside a longer run of letters and digits, so
 * that `BG-AVM-0020` is not found in `BG-AVM-00201` and an id is not found inside another.
 */
export function wordAt(text: string, word: string): number {
  let from = 0;
  for (;;) {
    const at = text.indexOf(word, from);
    if (at === -1) {
      return -1;
    }
    const before = at === 0 ? "" : (text[at - 1] ?? "");
    const after = text[at + word.length] ?? "";
    if (!WORD_CHARACTER.test(before) && !WORD_CHARACTER.test(after)) {
      return at;
    }
    from = at + 1;
  }
}

export interface Foreign {
  /** Codes, names, record numbers and ids that belong outside the member's scope. */
  readonly words: readonly string[];
  /** API paths whose answers are the catalogue of the scope itself and are read apart. */
  readonly apart: readonly RegExp[];
}

export interface Hit {
  readonly where: string;
  readonly word: string;
  readonly context: string;
}

/**
 * Where a page names something outside the member's scope: in its text, and in its API answers. A
 * word the member typed into the address herself is not looked for: a screen that says the id it
 * was asked for back to her tells her nothing.
 */
export function foreignHits(seen: Seen, foreign: Foreign): Hit[] {
  const hits: Hit[] = [];
  const read = seen.answers.filter(
    (answer) =>
      answer.status < 400 &&
      answer.body !== "" &&
      !foreign.apart.some((pattern) => pattern.test(answer.path)),
  );
  for (const word of foreign.words) {
    if (word === "" || seen.asked.includes(word)) {
      continue;
    }
    const inText = wordAt(seen.text, word);
    if (inText !== -1) {
      hits.push({ where: "the page's text", word, context: around(seen.text, inText) });
    }
    for (const answer of read) {
      const at = wordAt(answer.body, word);
      if (at !== -1) {
        hits.push({
          where: `${answer.method} ${answer.path}`,
          word,
          context: around(answer.body, at),
        });
      }
    }
  }
  return hits;
}

/** The hits in one line each, at most `limit` of them, with the count of the rest. */
export function hitsText(hits: readonly Hit[], limit = 4): string {
  const lines = hits.slice(0, limit).map((hit) => `${hit.word} in ${hit.where} ("${hit.context}")`);
  const rest = hits.length - lines.length;
  return rest > 0 ? `${lines.join("; ")}; and ${String(rest)} more` : lines.join("; ");
}

/** The failures of a page in one line, or "none". */
export function failuresText(seen: Seen, limit = 3): string {
  if (seen.failures.length === 0) {
    return "none";
  }
  const unique = [...new Set(seen.failures)];
  const shown = unique.slice(0, limit).join("; ");
  return unique.length > limit ? `${shown}; and ${String(unique.length - limit)} more` : shown;
}
