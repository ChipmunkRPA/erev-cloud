// Records the specs create when the world lacks them (docs/dev-guide.md DG-E2E-13; SCREENS_B §15;
// PRD §2.12). The demo seed holds no journal run and no SSP calculator run (R-RC-1), so the screens
// rows create theirs through the API and the crawl, which opens the routes of such records, finds
// them or creates them the same way.
import { randomUUID } from "node:crypto";

import { type APIRequestContext, expect } from "@playwright/test";

import { ApiClient, json, webOrigin } from "./api";

/** Polls the job named by a 202 `Location` header until it succeeds (04 API-C-12). */
export async function awaitJob(
  request: APIRequestContext,
  location: string | undefined,
): Promise<void> {
  if (location === undefined) {
    throw new Error("the 202 answer named no job");
  }
  const path = new URL(location, webOrigin()).pathname;
  await expect
    .poll(async () => (await json<{ readonly state: string }>(await request.get(path))).state, {
      timeout: 120_000,
      intervals: [1_000],
    })
    .toMatch(/^SUCCEEDED/);
}

export interface ListedSspBook {
  readonly id: string;
  readonly code: string;
  readonly current_version: {
    readonly id: string;
    readonly version_no: number;
    readonly legacy_version_label: string | null;
  } | null;
}

/** SCREENS_B §15: an SSP book resolved by code through the API. */
export async function sspBookByCode(
  request: APIRequestContext,
  code: string,
): Promise<ListedSspBook> {
  const listed = await json<{ readonly items: readonly ListedSspBook[] }>(
    await request.get("/api/v1/ssp-books", { params: { q: code, limit: 50 } }),
  );
  const book = listed.items.find((item) => item.code === code);
  if (book === undefined) {
    throw new Error(`SSP book ${code} is not visible to this persona`);
  }
  return book;
}

/** PRD §2.12 WLD-F-18, the bytes of `erev_api.domain.demo.fixtures.standalone_sales_pool()`. */
export function standaloneSalesPool(): Buffer {
  const days = [3, 9, 15, 21, 27];
  const customers = ["WLD-C-01", "WLD-C-02", "WLD-C-03", "WLD-C-08", "WLD-C-09", "WLD-C-12"];
  const lines = [
    "order_line_external_id,order_date,entity_code,customer_code,product_code,quantity,unit_price,currency",
  ];
  for (let index = 0; index < 40; index += 1) {
    const month = String(Math.floor(index / days.length) + 1).padStart(2, "0");
    const day = String(days[index % days.length] ?? 0).padStart(2, "0");
    const price = 73_000 + 2_000 * ((index * 17) % 40);
    lines.push(
      [
        `SO-AVM-2026-${String(index + 1).padStart(4, "0")}`,
        `2026-${month}-${day}`,
        "AVM-US",
        customers[index % customers.length] ?? "",
        "AVM-PLAT-100",
        "1",
        `${String(price)}.00`,
        "USD",
      ].join(","),
    );
  }
  return Buffer.from(`${lines.join("\n")}\n`, "utf-8");
}

/** SCREENS §11.5 sample world: the run over WLD-F-18. */
export const POOL_RUN_NAME = "AVM-PLAT-100 standalone sales 2026";

/**
 * SCREENS §11.5 (WLD-X-24): `maya` uploads WLD-F-18 as an IMPORT_SOURCE file and runs the calculator
 * over AVM-PLAT-100, 01 Jan 2026 to 31 Aug 2026, band 15%, book US-LIST; the run succeeds.
 */
export async function createPoolRun(request: APIRequestContext): Promise<string> {
  const client = new ApiClient(request);
  const book = await sspBookByCode(request, "US-LIST");
  const products = await json<{
    readonly items: readonly { readonly id: string; readonly code: string }[];
  }>(await client.get("/api/v1/products", { q: "AVM-PLAT-100", limit: 50 }));
  const product = products.items.find((item) => item.code === "AVM-PLAT-100");
  if (product === undefined) {
    throw new Error("product AVM-PLAT-100 is not visible to maya");
  }
  const uploaded = await request.fetch("/api/v1/files", {
    method: "POST",
    headers: {
      "X-CSRF-Token": await client.csrfToken(),
      "Idempotency-Key": randomUUID(),
      Origin: webOrigin(),
    },
    multipart: {
      purpose: "IMPORT_SOURCE",
      file: {
        name: "avm-plat-100-standalone-sales-2026.csv",
        mimeType: "text/csv",
        buffer: standaloneSalesPool(),
      },
    },
  });
  // Identical content of the same purpose answers with the stored file.
  expect([200, 201], await uploaded.text()).toContain(uploaded.status());
  const pool = (await uploaded.json()) as { readonly id: string };
  const created = await client.command("POST", "/api/v1/ssp-calculator-runs", {
    name: POOL_RUN_NAME,
    parameters: {
      source: "source_order_lines",
      product_ids: [product.id],
      date_from: "2026-01-01",
      date_to: "2026-08-31",
      band_ratio: "0.15",
      currency: "USD",
      ssp_book_id: book.id,
      pool_file_id: pool.id,
    },
  });
  expect(created.status(), await created.text()).toBe(202);
  const runId = created.headers()["x-erev-ssp-calculator-run-id"];
  if (runId === undefined) {
    throw new Error("POST /ssp-calculator-runs named no run");
  }
  await expect
    .poll(
      async () =>
        (
          await json<{ readonly status: string }>(
            await request.get(`/api/v1/ssp-calculator-runs/${runId}`),
          )
        ).status,
      { timeout: 90_000, intervals: [1_000] },
    )
    .toBe("SUCCEEDED");
  return runId;
}

/** The SSP calculator run over WLD-F-18: the one an SF-13 screens row created, else a new one. */
export async function ensurePoolRun(request: APIRequestContext): Promise<string> {
  const listed = await json<{
    readonly items: readonly {
      readonly id: string;
      readonly name: string;
      readonly status: string;
    }[];
  }>(await request.get("/api/v1/ssp-calculator-runs", { params: { limit: 200 } }));
  const run = listed.items.find(
    (item) => item.name === POOL_RUN_NAME && item.status === "SUCCEEDED",
  );
  return run === undefined ? createPoolRun(request) : run.id;
}

interface ListedJournalRun {
  readonly id: string;
  readonly state: string;
  readonly created_at: string;
}

async function earliestJournalRun(
  request: APIRequestContext,
): Promise<ListedJournalRun | undefined> {
  const listed = await json<{ readonly items: readonly ListedJournalRun[] }>(
    await request.get("/api/v1/journal-runs", {
      params: { entity: "AVM-US", book: "ASC606", limit: 200 },
    }),
  );
  return [...listed.items]
    .filter((item) => item.state !== "cancelled")
    .sort((left, right) => (left.created_at < right.created_at ? -1 : 1))[0];
}

/**
 * The earliest AVM-US ASC 606 journal run that is not cancelled: the one RC-SMOKE.7 or an SF-06
 * screens row calculated, else the Aug 2026 run calculated here as the SF-06 rows calculate it. A
 * 409 means another worker is calculating it, so its run is awaited.
 */
export async function ensureJournalRun(request: APIRequestContext): Promise<string> {
  let run = await earliestJournalRun(request);
  if (run === undefined) {
    const created = await new ApiClient(request).command("POST", "/api/v1/journal-runs", {
      entity_code: "AVM-US",
      period_key: "FY2026-P08",
      book: "ASC606",
    });
    expect([202, 409], await created.text()).toContain(created.status());
    if (created.status() === 202) {
      await awaitJob(request, created.headers()["location"]);
    }
    await expect
      .poll(async () => (await earliestJournalRun(request))?.id, {
        timeout: 120_000,
        intervals: [1_000],
      })
      .toBeDefined();
    run = await earliestJournalRun(request);
  }
  if (run === undefined) {
    throw new Error("POST /journal-runs created no AVM-US run");
  }
  return run.id;
}
