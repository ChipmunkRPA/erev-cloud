// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeAll, beforeEach, expect, it, vi } from "vitest";
import { SCREEN_ROUTES } from "../../../app/router";
import { type EvidencePack, mayDownloadEvidence } from "../../../lib/api/queries/evidence-packs";
import { accessOf } from "../../../lib/access";
import { installMemoryStorage, preloadScreens, renderApp, signedInMe } from "../../../test/app";
import { installGridViewport } from "../../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";

installMswServer();
installMemoryStorage();
installGridViewport();
beforeAll(async () => {
  await preloadScreens(SCREEN_ROUTES, ["SF-09", "SF-09:pack"]);
});
beforeEach(() => {
  server.use(
    http.get(apiUrl("/api/v1/report-definitions"), () => HttpResponse.json({ items: [] })),
  );
});
afterEach(() => cleanup());
const permissions = [
  "report.run",
  "audit.read",
  "contract.read",
  "report.export",
  "evidence.export",
];
const me = signedInMe({ permissions });
const pack: EvidencePack = {
  id: "11111111-1111-4111-8111-111111111111",
  pack_no: "EVP-000014",
  kind: "CLOSE",
  status: "SUCCEEDED",
  entity_id: "22222222-2222-4222-8222-222222222222",
  entity_code: "AVM-US",
  book: "ASC606",
  period_id: "33333333-3333-4333-8333-333333333333",
  period_key: "FY2026-P09",
  period_lock_id: "44444444-4444-4444-8444-444444444444",
  job_id: null,
  file_count: 1,
  created_at: "2026-10-01T10:00:00Z",
  updated_at: "2026-10-01T10:05:00Z",
  report_run_ids: [],
  manifest: {
    files: [
      { path: "certification/lock.json", bytes: 123, sha256: "a".repeat(64), report_run_id: null },
    ],
  },
  manifest_sha256: "b".repeat(64),
  download_href: "/api/v1/evidence-packs/11111111-1111-4111-8111-111111111111/download",
};
function open(detail = true, member = me) {
  return renderApp(detail ? `/reports/evidence/${pack.id}` : "/reports/evidence", {
    me: member,
    screenRoutes: SCREEN_ROUTES,
  });
}
function serve(value = pack) {
  server.use(http.get(apiUrl(`/api/v1/evidence-packs/${pack.id}`), () => HttpResponse.json(value)));
}
it("shows retained identity and every manifest hash", async () => {
  serve();
  open();
  expect(await screen.findByRole("heading", { name: pack.pack_no })).not.toBeNull();
  expect(screen.getByText(pack.entity_code)).not.toBeNull();
  expect(screen.getByText(pack.period_key)).not.toBeNull();
  expect(screen.getByText("certification/lock.json")).not.toBeNull();
  expect(screen.getByText("a".repeat(64))).not.toBeNull();
  expect(screen.getByText("b".repeat(64))).not.toBeNull();
  expect(screen.getByRole("button", { name: "Download pack" })).not.toBeNull();
  expect(screen.getByRole("button", { name: "Download manifest" })).not.toBeNull();
});
it.each(["QUEUED", "RUNNING", "FAILED"] as const)(
  "does not offer an archive for %s",
  async (status) => {
    serve({
      ...pack,
      status,
      file_count: null,
      manifest: null,
      manifest_sha256: null,
      download_href: null,
    });
    open();
    await screen.findByRole("heading", { name: pack.pack_no });
    expect(screen.queryByRole("button", { name: "Download pack" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Download manifest" })).toBeNull();
    expect(screen.queryByText("a".repeat(64))).toBeNull();
  },
);
it("does not fetch packs when a source permission is missing", async () => {
  let reads = 0;
  server.use(
    http.get(apiUrl(`/api/v1/evidence-packs/${pack.id}`), () => {
      reads++;
      return HttpResponse.json(pack);
    }),
  );
  open(true, signedInMe({ permissions: ["report.run"] }));
  expect(await screen.findByText("Evidence pack access is limited")).not.toBeNull();
  expect(reads).toBe(0);
});
it("requires every export permission in the pack's entity scope", () => {
  for (const missing of permissions) {
    const scoped = signedInMe({
      permissions,
      permission_scopes: Object.fromEntries(
        permissions.map((p) => [p, p === missing ? ["other-entity"] : "*"]),
      ),
    });
    expect(mayDownloadEvidence(accessOf(scoped), pack)).toBe(false);
  }
  expect(mayDownloadEvidence(accessOf(me), pack)).toBe(true);
});
it.each(["download", "manifest"] as const)(
  "shows a %s refusal without saving its response",
  async (artifact) => {
    serve();
    let requests = 0;
    server.use(
      http.get(apiUrl(`/api/v1/evidence-packs/${pack.id}/${artifact}`), () => {
        requests++;
        return problemResponse("validation-failed", 422, "Archive verification failed");
      }),
    );
    open();
    fireEvent.click(
      await screen.findByRole("button", {
        name: artifact === "manifest" ? "Download manifest" : "Download pack",
      }),
    );
    expect(await screen.findByText("Could not download the evidence pack")).not.toBeNull();
    await waitFor(() => expect(requests).toBe(1));
  },
);
it("lists pack identities and opens the retained record", async () => {
  server.use(
    http.get(apiUrl("/api/v1/evidence-packs"), () =>
      HttpResponse.json(
        { items: [pack], next_cursor: null },
        { headers: { "X-Erev-Total-Count": "1" } },
      ),
    ),
  );
  open(false);
  expect((await screen.findByRole("link", { name: pack.pack_no })).getAttribute("href")).toBe(
    `/reports/evidence/${pack.id}?entity=AVM-US&book=ASC606&period=FY2026-P09`,
  );
  expect(screen.getByRole("columnheader", { name: /Manifest SHA-256/ })).not.toBeNull();
  expect(screen.getByRole("columnheader", { name: /^Files/ })).not.toBeNull();
  expect(screen.getByText("b".repeat(64))).not.toBeNull();
  expect(screen.getByRole("button", { name: "Copy output SHA-256" })).not.toBeNull();
});
it("shows not found for missing or inaccessible IDs", async () => {
  server.use(
    http.get(apiUrl(`/api/v1/evidence-packs/${pack.id}`), () =>
      problemResponse("not-found", 404, "Not found"),
    ),
  );
  open();
  expect(await screen.findByText("Evidence pack not found")).not.toBeNull();
});

it("passes context and decoded status filters to the scoped API", async () => {
  const reads: URL[] = [];
  server.use(
    http.get(apiUrl("/api/v1/evidence-packs"), ({ request }) => {
      reads.push(new URL(request.url));
      return HttpResponse.json({ items: [], next_cursor: null });
    }),
  );
  renderApp(
    "/reports/evidence?entity=AVM-US&book=ASC606&period=FY2026-P09&f.status=in:QUEUED,FAILED",
    { me, screenRoutes: SCREEN_ROUTES },
  );
  await waitFor(() => expect(reads.length).toBeGreaterThan(0));
  expect(reads.length).toBeGreaterThan(0);
  const first = reads[0];
  if (first === undefined) throw new Error("No evidence register request recorded");
  const query = first.searchParams;
  expect(query.getAll("entity")).toEqual(["AVM-US"]);
  expect(query.get("book")).toBe("ASC606");
  expect(query.get("period")).toBe("FY2026-P09");
  expect(query.getAll("status")).toEqual(["QUEUED", "FAILED"]);
  expect(query.get("kind")).toBe("CLOSE");
});

it("hides download when the member can read but cannot export", async () => {
  serve();
  open(true, signedInMe({ permissions: ["report.run", "audit.read", "contract.read"] }));
  await screen.findByRole("heading", { name: pack.pack_no });
  expect(screen.getByText("certification/lock.json")).not.toBeNull();
  expect(screen.queryByRole("button", { name: "Download pack" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Download manifest" })).toBeNull();
});

it("shows the retained lock, missing sections and separately retained manifest", async () => {
  serve();
  open();
  await screen.findByRole("heading", { name: pack.pack_no });
  expect(screen.getByText(pack.period_lock_id)).not.toBeNull();
  const contents = screen.getByRole("table", { name: "Contents" });
  const certification = within(contents).getByRole("row", { name: /Close certification/ });
  expect(within(certification).getByText("Missing")).not.toBeNull();
  expect(within(certification).getByText("certification.json")).not.toBeNull();
  const manifest = within(contents).getByRole("row", { name: /^Manifest Present/ });
  expect(within(manifest).getByText("Present")).not.toBeNull();
  expect(within(contents).queryByText(/Re-lock/)).toBeNull();
});

it("copies the exact per-file and manifest hashes with named keyboard controls", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  const previous = Object.getOwnPropertyDescriptor(navigator, "clipboard");
  Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
  try {
    serve();
    open();
    const copy = await screen.findByRole("button", {
      name: "Copy SHA-256 of certification/lock.json",
    });
    expect(copy.tabIndex).toBe(0);
    fireEvent.click(copy);
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("a".repeat(64)));
    fireEvent.click(screen.getByRole("button", { name: "Copy SHA-256 of manifest.json" }));
    await waitFor(() => expect(writeText).toHaveBeenCalledWith("b".repeat(64)));
  } finally {
    if (previous) Object.defineProperty(navigator, "clipboard", previous);
    else Reflect.deleteProperty(navigator, "clipboard");
  }
});

const firstClosePaths = [
  "certification.json",
  "lock/snapshots.json",
  "lock/approvals.json",
  "lock/source_binding.json",
  "journals/batch_register.json",
  "journals/je_population.csv",
  "reconciliations/index.json",
  "reconciliations/population.json",
  "audit/chain_digest.json",
  "audit/sources.json",
  "reports/revenue_waterfall.csv",
  "reports/contract_balances.csv",
  "reports/contract_balance_rollforward.csv",
  "reports/rpo.csv",
  "reports/rpo_rollforward.csv",
  "reports/disaggregation.csv",
  "reports/revenue_from_prior_period_obligations.csv",
  "reports/contract_cost_rollforward.csv",
  "registers/out_of_period.csv",
  "registers/modification_register.csv",
  "registers/manual_adjustment_register.csv",
  ...[
    "registers/ssp_change_log",
    "registers/config_change_register",
    "registers/late_entries",
    "access/user_access_listing",
    "access/sod_conflict_report",
  ].flatMap((prefix) =>
    ["csv", "manifest.json", "source.json"].map((suffix) => `${prefix}.${suffix}`),
  ),
];
it("requires every member of combined sections, including supporting source evidence", async () => {
  const missing = "access/sod_conflict_report.source.json";
  serve({
    ...pack,
    manifest: {
      files: firstClosePaths
        .filter((path) => path !== missing)
        .map((path) => ({
          path,
          bytes: 123,
          sha256: "a".repeat(64),
          report_run_id: null,
        })),
    },
  });
  open();
  await screen.findByRole("heading", { name: pack.pack_no });
  const contents = screen.getByRole("table", { name: "Contents" });
  expect(within(contents).getAllByText("Missing")).toHaveLength(1);
  const access = within(contents).getByRole("row", { name: /User listing and SoD/ });
  expect(within(access).getByText(missing)).not.toBeNull();
  expect(within(contents).getAllByText("Present")).toHaveLength(11);
});
it("shows a complete first-close contents list without expecting a self-hashed manifest", async () => {
  serve({
    ...pack,
    manifest: {
      files: firstClosePaths.map((path) => ({
        path,
        bytes: 123,
        sha256: "a".repeat(64),
        report_run_id: null,
      })),
    },
  });
  open();
  await screen.findByRole("heading", { name: pack.pack_no });
  const contents = screen.getByRole("table", { name: "Contents" });
  expect(within(contents).queryByText("Missing")).toBeNull();
  expect(within(contents).getAllByText("Present")).toHaveLength(12);
});
