// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, expect, it } from "vitest";
import { GenerateClosePack } from "../generate";
import type { Entity, Period, Book } from "../../../lib/api/queries/tenant";
import type { PeriodLockRow } from "../../../lib/api/queries/periods";
import type { Job } from "../../../lib/api/jobs";
import { installMemoryStorage, probeRoute, renderApp, signedInMe } from "../../../test/app";
import { installMswServer, apiUrl, server, problemResponse } from "../../../test/msw";
installMswServer();
installMemoryStorage();
afterEach(() => cleanup());
const id = (n: number) => `00000000-0000-4000-8000-${String(n).padStart(12, "0")}`;
const now = "2026-10-01T10:00:00Z";
const permissions = [
  "report.run",
  "report.export",
  "evidence.export",
  "audit.read",
  "contract.read",
  "config.read",
];
const me = signedInMe({ permissions });
const entity: Entity = {
  id: id(1),
  code: "AVM-US",
  name: "Avenmoor US",
  books: [
    {
      id: id(2),
      entity_id: id(1),
      book_code: "ASC606",
      first_period_id: id(3),
      first_period_key: "FY2026-P09",
      is_enabled: true,
      row_version: 1,
      created_at: now,
      updated_at: now,
    },
  ],
  calendar_id: id(4),
  country_code: "US",
  functional_currency: "USD",
  is_active: true,
  parent_entity_id: null,
  row_version: 1,
  tax_id: null,
  time_zone: "UTC",
  created_at: now,
  updated_at: now,
};
const book: Book = {
  id: id(5),
  code: "ASC606",
  name: "ASC 606",
  is_enabled: true,
  is_primary: true,
  posting_target: "GL_PRIMARY",
  row_version: 1,
  created_at: now,
  updated_at: now,
};
const period: Period = {
  id: id(6),
  entity: { id: entity.id, code: entity.code, name: entity.name },
  book: "ASC606",
  period: {
    id: id(3),
    period_key: "FY2026-P09",
    name: "Sep 2026",
    fiscal_year: 2026,
    period_no: 9,
    quarter_no: 3,
    start_date: "2026-09-01",
    end_date: "2026-09-30",
  },
  state: "closed",
  row_version: 1,
  state_changed_at: now,
  is_first_open: false,
  current_lock: null,
  close_run: null,
  blockers: null,
};
const lock: PeriodLockRow = {
  id: id(7),
  kind: "LOCK",
  previous_lock_id: null,
  approval_request_id: id(8),
  approval_request_no: "APR-000001",
  audit_head_chain_seq: 1,
  certification: [],
  comment: null,
  created_at: now,
  created_by: { id: me.user.id, display_name: me.user.display_name, kind: "USER" },
  cutoff_known_at: now,
  diff_report_file_id: null,
  ledger_head_chain_seq: 1,
  ledger_head_sha256: "a".repeat(64),
  reason_code: null,
  snapshot_manifest_sha256: "b".repeat(64),
  snapshots: [],
};
const job: Job = {
  id: id(9),
  kind: "EVIDENCE_PACK",
  state: "QUEUED",
  created_at: now,
  created_by: lock.created_by,
  started_at: null,
  finished_at: null,
  problem: null,
  progress: { done: 0, total: null },
  result: null,
};
const packId = id(10);
const routes = [
  {
    id: "SF-09",
    path: "/reports/evidence",
    handle: { sf: "SF-09", screen: "SF-09", titleKey: "evidence.packs.title" },
    Component: GenerateClosePack,
  },
  probeRoute("SF-09:pack", "/reports/evidence/:packId", "evidence.packs.detailTitle"),
];
const list = (items: readonly unknown[], next_cursor: string | null = null) =>
  HttpResponse.json({ items, next_cursor });
beforeEach(() =>
  server.use(
    http.get(apiUrl("/api/v1/entities"), () => list([entity])),
    http.get(apiUrl("/api/v1/books"), () => list([book])),
    http.get(apiUrl("/api/v1/periods"), () => list([period])),
    http.get(apiUrl(`/api/v1/periods/${period.id}/locks`), () => list([lock])),
    http.get(apiUrl(`/api/v1/jobs/${job.id}`), () => HttpResponse.json(job)),
    http.get(apiUrl("/api/v1/me/notifications"), () => list([])),
  ),
);
function open(member = me) {
  return renderApp("/reports/evidence?entity=AVM-US&book=ASC606&period=FY2026-P09", {
    me: member,
    screenRoutes: routes,
  });
}
async function chooseLock() {
  fireEvent.click(await screen.findByRole("button", { name: "Generate close evidence pack" }));
  const dialog = await screen.findByRole("dialog");
  const field = within(dialog).getByRole("combobox", { name: /Retained lock/ });
  await waitFor(() => {
    fireEvent.keyDown(field, { key: "ArrowDown" });
    expect(screen.getByRole("option", { name: /APR-000001/ })).not.toBeNull();
  });
  fireEvent.mouseDown(screen.getByRole("option", { name: /APR-000001/ }));
  await waitFor(() =>
    expect(
      within(dialog).getByRole("button", { name: "Generate pack" }).getAttribute("aria-disabled"),
    ).toBeNull(),
  );
  return dialog;
}
function accepted() {
  return HttpResponse.json(job, {
    status: 202,
    headers: { Location: `/api/v1/jobs/${job.id}`, "X-Erev-Evidence-Pack-Id": packId },
  });
}
it("submits exact retained selectors with an idempotency key and opens the new pack", async () => {
  const bodies: unknown[] = [];
  const keys: (string | null)[] = [];
  server.use(
    http.post(apiUrl("/api/v1/evidence-packs"), async ({ request }) => {
      bodies.push(await request.json());
      keys.push(request.headers.get("Idempotency-Key"));
      return accepted();
    }),
  );
  const app = open();
  const dialog = await chooseLock();
  fireEvent.click(within(dialog).getByRole("button", { name: "Generate pack" }));
  await waitFor(() =>
    expect(app.router.state.location.pathname).toBe(`/reports/evidence/${packId}`),
  );
  expect(app.router.state.location.search).toBe("?entity=AVM-US&book=ASC606&period=FY2026-P09");
  expect(bodies).toEqual([
    {
      kind: "CLOSE",
      entity_code: "AVM-US",
      book: "ASC606",
      period_key: "FY2026-P09",
      period_lock_id: lock.id,
    },
  ]);
  expect(keys[0]).toMatch(/^[0-9a-f-]{36}$/i);
});
it("requires explicit lock selection and excludes re-lock/reopen records", async () => {
  server.use(
    http.get(apiUrl(`/api/v1/periods/${period.id}/locks`), () =>
      list([
        { ...lock, id: id(11), previous_lock_id: lock.id, approval_request_no: "APR-RELOCK" },
        { ...lock, id: id(12), kind: "REOPEN", approval_request_no: "APR-REOPEN" },
        lock,
      ]),
    ),
  );
  open();
  fireEvent.click(await screen.findByRole("button", { name: "Generate close evidence pack" }));
  const dialog = await screen.findByRole("dialog");
  expect(
    within(dialog).getByRole("button", { name: "Generate pack" }).getAttribute("aria-disabled"),
  ).toBe("true");
  const field = within(dialog).getByRole("combobox", { name: /Retained lock/ });
  await waitFor(() => {
    fireEvent.keyDown(field, { key: "ArrowDown" });
    expect(screen.getByRole("option", { name: /APR-000001/ })).not.toBeNull();
  });
  expect(screen.queryByRole("option", { name: /APR-RELOCK|APR-REOPEN/ })).toBeNull();
});
it.each(["report.export", "evidence.export", "config.read"])(
  "hides generation without %s",
  async (permission) => {
    open(signedInMe({ permissions: permissions.filter((p) => p !== permission) }));
    expect(screen.queryByRole("button", { name: "Generate close evidence pack" })).toBeNull();
  },
);
it("keeps the same intent key after a lost response, including closing and reopening", async () => {
  const keys: (string | null)[] = [];
  server.use(
    http.post(apiUrl("/api/v1/evidence-packs"), ({ request }) => {
      keys.push(request.headers.get("Idempotency-Key"));
      return keys.length === 1 ? HttpResponse.error() : accepted();
    }),
  );
  const app = open();
  let dialog = await chooseLock();
  fireEvent.click(within(dialog).getByRole("button", { name: "Generate pack" }));
  await screen.findByText(/The response was lost/);
  fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
  fireEvent.click(screen.getByRole("button", { name: "Generate close evidence pack" }));
  dialog = await screen.findByRole("dialog");
  fireEvent.keyDown(within(dialog).getByRole("combobox", { name: /Retained lock/ }), {
    key: "ArrowDown",
  });
  fireEvent.mouseDown(screen.getByRole("option", { name: /APR-000001/ }));
  fireEvent.click(within(dialog).getByRole("button", { name: "Generate pack" }));
  await waitFor(() =>
    expect(app.router.state.location.pathname).toBe(`/reports/evidence/${packId}`),
  );
  expect(keys).toHaveLength(2);
  expect(keys[0]).toBe(keys[1]);
});
it("shows a backend refusal without navigating or pretending generation succeeded", async () => {
  server.use(
    http.post(apiUrl("/api/v1/evidence-packs"), () =>
      problemResponse("validation-failed", 422, "Close evidence is incomplete"),
    ),
  );
  const app = open();
  const dialog = await chooseLock();
  fireEvent.click(within(dialog).getByRole("button", { name: "Generate pack" }));
  await screen.findByText("Close evidence is incomplete");
  expect(app.router.state.location.pathname).toBe("/reports/evidence");
});

it("follows source pagination instead of losing historical periods beyond the first page", async () => {
  const cursors: (string | null)[] = [];
  server.use(
    http.get(apiUrl("/api/v1/periods"), ({ request }) => {
      const cursor = new URL(request.url).searchParams.get("cursor");
      cursors.push(cursor);
      return cursor === null ? list([], "next-period-page") : list([period]);
    }),
  );
  open();
  await chooseLock();
  expect(cursors).toContain("next-period-page");
});

it("requires every export permission in the chosen entity scope", async () => {
  const member = signedInMe({
    permissions,
    permission_scopes: Object.fromEntries(
      permissions.map((p) => [p, p === "report.export" ? [id(99)] : "*"]),
    ),
  });
  open(member);
  fireEvent.click(await screen.findByRole("button", { name: "Generate close evidence pack" }));
  const dialog = await screen.findByRole("dialog");
  fireEvent.keyDown(within(dialog).getByRole("combobox", { name: /Entity/ }), { key: "ArrowDown" });
  await screen.findByText("No matches");
  expect(screen.queryByRole("option", { name: /AVM-US/ })).toBeNull();
  expect(
    within(dialog).getByRole("button", { name: "Generate pack" }).getAttribute("aria-disabled"),
  ).toBe("true");
});

it("does not resubmit an accepted response whose navigation headers are missing", async () => {
  let submissions = 0;
  server.use(
    http.post(apiUrl("/api/v1/evidence-packs"), () => {
      submissions++;
      return HttpResponse.json(job, { status: 202 });
    }),
  );
  open();
  const dialog = await chooseLock();
  const button = within(dialog).getByRole("button", { name: "Generate pack" });
  fireEvent.click(button);
  await screen.findByRole("heading", {
    name: "The request was accepted. Check the evidence register for the new pack.",
  });
  const acceptedButton = within(dialog).getByRole("button", { name: "Generate pack" });
  expect(acceptedButton.getAttribute("aria-disabled")).toBe("true");
  fireEvent.click(acceptedButton);
  expect(submissions).toBe(1);
});

it("keeps authorized historical sources available when their entity or book is now inactive", async () => {
  let unfilteredRead = false;
  server.use(
    http.get(apiUrl("/api/v1/entities"), ({ request }) => {
      if (!new URL(request.url).searchParams.has("is_active")) unfilteredRead = true;
      return list([
        {
          ...entity,
          is_active: false,
          books: entity.books.map((item) => ({ ...item, is_enabled: false })),
        },
      ]);
    }),
  );
  open();
  const dialog = await chooseLock();
  expect(unfilteredRead).toBe(true);
  expect(
    (within(dialog).getByRole("combobox", { name: /Entity/ }) as HTMLInputElement).value,
  ).toContain("(inactive)");
  expect(
    (within(dialog).getByRole("combobox", { name: /Book/ }) as HTMLInputElement).value,
  ).toContain("(inactive)");
});
