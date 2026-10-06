// @vitest-environment jsdom
// SF-09:audit-log and SF-09:verification (BUILD_SPEC RPS-21; SCREENS_B §6.3, §6.4, §0.4 E-98; SCREENS §0.3
// SCR-IA-02, §0.7 SCR-ST-06, SCR-ST-07; 04 API-R-10; docs/dev-guide.md DG-KRN-AUD-05): the event drawer
// shows the changed fields of an event only and redacted keys as "[REDACTED]"; "Verify chain now" starts
// the verification job, shows its progress in the header and ends with the chip Verified, the event count
// and the last chain value; the list is read over a stated range; the object filter resolves a contract's
// business id; the verification record shows its figures, the digest link and the failure detail. Item
// AUD-SCREEN-BIND-1 (SCREENS_B rev 1.57; 04 rev 1.154): the Outcome chip, the trail of a contract, an
// event read alone by its sequence, the object's business label, the actor's link and the names of the
// Actor filter, and a verification read by its id.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { SCREEN_ROUTES } from "../../../app/router";
import type { AuditEvent, AuditVerification } from "../../../lib/api/queries/audit";
import { accessOf } from "../../../lib/access";
import { accessDescription } from "../../../test/access";
import { installMemoryStorage, preloadScreens, renderApp, signedInMe } from "../../../test/app";
import { narrowColumns } from "../../../test/grid-headers";
import { installGridViewport } from "../../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";
import { actorOptions, auditColumns, auditFilterFields } from "../audit-log";
import { eventChanges } from "../event-drawer";

installMswServer();
installMemoryStorage();
installGridViewport();

beforeAll(async () => {
  await preloadScreens(SCREEN_ROUTES, ["SF-09:audit-log", "SF-09:verification", "SF-08"]);
});

// 12 Sep 2026 16:40 UTC: the default range is 13 Aug 2026 to 12 Sep 2026.
const NOW = Date.UTC(2026, 8, 12, 16, 40, 0);

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const HANNAH_ID = "6d2e9b8f-3c5a-4d7e-8f9b-8a7c6d5e4f3b";
const PRIYA_ID = "7e3f0c9a-4d6b-4e8f-9a0c-9b8d7e6f5a4c";
const HANNAH = signedInMe({
  user: {
    id: HANNAH_ID,
    email: "hannah@example.test",
    display_name: "Hannah Lindqvist",
    status: "ACTIVE",
  },
  permissions: ["contract.read", "report.run", "report.export", "evidence.export", "audit.read"],
});

const CONTRACT_ID = "1f2e3d4c-5b6a-4978-8695-a4b3c2d1e0f9";
const MODIFICATION_ID = "2a3b4c5d-6e7f-4a8b-9c0d-1e2f3a4b5c6d";
const EVENT_APPROVE = "9c8b7a69-5847-4362-9514-03f2e1d0c9b8";
const EVENT_BOOK = "0d9c8b7a-6958-4473-8625-14a3f2e1d0c9";
const EVENT_DENIED = "1e0d9c8b-7a69-4584-9736-25b4a3f2e1d0";
const JOB_ID = "3b4c5d6e-7f8a-4b9c-8d0e-2f3a4b5c6d7e";
const SCHEDULED_ID = "4c5d6e7f-8a9b-4c0d-9e1f-3a4b5c6d7e8f";
const ON_DEMAND_ID = "5d6e7f8a-9b0c-4d1e-8f2a-4b5c6d7e8f9a";
const FAILED_ID = "6e7f8a9b-0c1d-4e2f-9a3b-5c6d7e8f9a0b";
const DIGEST_FILE_ID = "7f8a9b0c-1d2e-4f3a-8b4c-6d7e8f9a0b1c";
const LAST_HMAC = `1a09e4b2${"0".repeat(52)}7c21`;

function event(overrides: Partial<AuditEvent>): AuditEvent {
  return {
    id: EVENT_APPROVE,
    chain_seq: 9104,
    occurred_at: "2026-09-10T15:22:41.318204Z",
    actor: { id: PRIYA_ID, kind: "USER", display_name: "Priya Raman" },
    actor_membership_id: null,
    actor_roles: ["revenue_reviewer"],
    auth_method: "password",
    mfa_verified: true,
    on_behalf_of: null,
    api_client_id: null,
    support_grant_id: null,
    source_ip: "10.20.30.40",
    request_id: "5f4e3d2c-1b0a-4f9e-8d7c-6b5a4f3e2d1c",
    action: "modification.approve",
    object_type: "modification",
    object_id: MODIFICATION_ID,
    object_label: null,
    object_version: "3",
    before: null,
    after: null,
    diff: null,
    reason_code: null,
    comment: null,
    approval_request_id: null,
    outcome: "SUCCESS",
    detail: {},
    prev_hmac: `88e0${"1".repeat(60)}`,
    hmac: LAST_HMAC,
    hmac_key_id: "audit-hmac:1",
    ...overrides,
  };
}

/** PRD J-17.5: the approval of the modification, with a redacted credential key and an unchanged memo. */
const APPROVED = event({
  before: { status: "SUBMITTED", memo: "Q3 true-up", terms: { end_date: "2026-12-31" } },
  after: {
    status: "APPROVED",
    memo: "Q3 true-up",
    terms: { end_date: "2027-06-30" },
    client_secret_ref: "[REDACTED]",
  },
  diff: [
    { path: "status", before: "SUBMITTED", after: "APPROVED" },
    { path: "terms.end_date", before: "2026-12-31", after: "2027-06-30" },
    { path: "client_secret_ref", before: null, after: "[REDACTED]" },
  ],
  comment: "Agreed with the customer on 08 Sep 2026.",
  detail: { authorization: "[REDACTED]", step: 1 },
});

const BOOKED = event({
  id: EVENT_BOOK,
  chain_seq: 9097,
  occurred_at: "2026-09-10T14:05:02.000000Z",
  actor: { id: null, kind: "SYSTEM", display_name: "System" },
  actor_roles: [],
  auth_method: "system",
  mfa_verified: null,
  action: "contract.book",
  object_type: "contract",
  object_id: CONTRACT_ID,
  prev_hmac: null,
});

/** PRD J-17.7: a refused approval decision. */
const DENIED = event({
  id: EVENT_DENIED,
  chain_seq: 9090,
  occurred_at: "2026-09-09T09:00:00.000000Z",
  actor: { id: HANNAH_ID, kind: "USER", display_name: "Hannah Lindqvist" },
  actor_roles: ["auditor"],
  action: "approval_request.decide",
  object_type: "approval_request",
  object_id: null,
  outcome: "DENIED",
  detail: { permission: "modification.approve" },
});

const CLIENT_ID = "2f1e0d9c-8b7a-4695-8a47-36c5b4a3f2e1";
const OPERATOR_ID = "3a2f1e0d-9c8b-47a6-9b58-47d6c5b4a3f2";
const MAYA_ID = "4b3a2f1e-0d9c-48b7-8c69-58e7d6c5b4a3";
const GRANT_ID = "5c4b3a2f-1e0d-49c8-9d7a-69f8e7d6c5b4";
const EVENT_CLIENT = "6d5c4b3a-2f1e-4ad9-8e8b-7a09f8e7d6c5";
const EVENT_OPERATOR = "7e6d5c4b-3a2f-4bea-9f9c-8b1a09f8e7d6";
const EVENT_FOR_MAYA = "8f7e6d5c-4b3a-4cfb-8a0d-9c2b1a09f8e7";
const EVENT_FOR_CLIENT = "9a8f7e6d-5c4b-4d0c-9b1e-0d3c2b1a09f8";
const SYSTEM = { id: null, kind: "SYSTEM", display_name: "System" } as const;

/** 04 §16.14: an event of an API client carries the client's name in `actor.display_name`. */
const BY_CLIENT = event({
  id: EVENT_CLIENT,
  chain_seq: 9080,
  occurred_at: "2026-09-08T11:00:00.000000Z",
  actor: { id: CLIENT_ID, kind: "API_CLIENT", display_name: "Billing sync" },
  actor_roles: [],
  auth_method: "oauth_client",
  mfa_verified: null,
  api_client_id: CLIENT_ID,
  action: "import_upload.create",
  object_type: "import_upload",
  object_id: null,
});
/** An operator who acted under a support grant: the Actor carries the operator's own name. */
const BY_OPERATOR = event({
  id: EVENT_OPERATOR,
  chain_seq: 9070,
  occurred_at: "2026-09-08T10:00:00.000000Z",
  actor: { id: OPERATOR_ID, kind: "OPERATOR", display_name: "Dana Whitfield" },
  actor_roles: [],
  support_grant_id: GRANT_ID,
  action: "contract.read",
  object_type: "contract",
  object_id: null,
});
/** Steps the system ran for the creator of their job: a member, and an API client. */
const FOR_MAYA = event({
  id: EVENT_FOR_MAYA,
  chain_seq: 9060,
  occurred_at: "2026-09-08T09:00:00.000000Z",
  actor: SYSTEM,
  actor_roles: [],
  auth_method: "system",
  mfa_verified: null,
  on_behalf_of: { id: MAYA_ID, kind: "USER", display_name: "Maya Chen" },
  action: "report_run.complete",
  object_type: "report_run",
  object_id: null,
});
const FOR_CLIENT = event({
  id: EVENT_FOR_CLIENT,
  chain_seq: 9050,
  occurred_at: "2026-09-08T08:00:00.000000Z",
  actor: SYSTEM,
  actor_roles: [],
  auth_method: "system",
  mfa_verified: null,
  on_behalf_of: { id: CLIENT_ID, kind: "API_CLIENT", display_name: "Billing sync" },
  action: "import_upload.commit",
  object_type: "import_upload",
  object_id: null,
});

/** An event of March: older than any range the list reads by default. */
const OLD_SEQUENCE = 412;
const ROLE_ID = "2d1c0b9a-8f7e-4a3f-8e4b-3a6f5e4d3c2b";
const OLD = event({
  id: "3e2d1c0b-9a8f-4b4a-9f5c-4b7a6f5e4d3c",
  chain_seq: OLD_SEQUENCE,
  occurred_at: "2026-03-02T08:15:00.000000Z",
  action: "role.update",
  object_type: "role",
  object_id: ROLE_ID,
  object_label: "revenue_reviewer",
});

const PRIYA_MEMBERSHIP = "4f3e2d1c-0b9a-4c5b-8a6d-5c8b7a6f5e4d";
const MAYA_MEMBERSHIP = "5a4f3e2d-1c0b-4d6c-9b7e-6d9c8b7a6f5e";
const PRIYA = { id: PRIYA_ID, kind: "USER", display_name: "Priya Raman" } as const;
const HANNAH_ACTOR = { id: HANNAH_ID, kind: "USER", display_name: "Hannah Lindqvist" } as const;

const REPORT_RUN_ID = "0b9a8f7e-6d5c-4e1d-8c2f-1e4d3c2b1a09";
/** The completion of a report run Maya started: the object is the run, named by its id. */
const FOR_MAYA_ON_RUN = event({
  ...FOR_MAYA,
  id: "1c0b9a8f-7e6d-4f2e-9d3a-2f5e4d3c2b1a",
  chain_seq: 9061,
  object_id: REPORT_RUN_ID,
});

function verification(overrides: Partial<AuditVerification>): AuditVerification {
  return {
    id: SCHEDULED_ID,
    trigger: "SCHEDULED",
    from_chain_seq: 1,
    to_chain_seq: 9050,
    events_checked: 9050,
    result: "PASS",
    first_failure_seq: null,
    failure_detail: null,
    digest_last_hmac: `77aa${"2".repeat(60)}`,
    digest_file_id: "8a9b0c1d-2e3f-4a4b-9c5d-7e8f9a0b1c2d",
    job_id: null,
    started_at: "2026-09-12T02:00:00.000000Z",
    finished_at: "2026-09-12T02:00:06.000000Z",
    ...overrides,
  };
}

const SCHEDULED = verification({});
const ON_DEMAND = verification({
  id: ON_DEMAND_ID,
  trigger: "ON_DEMAND",
  to_chain_seq: 9112,
  events_checked: 9112,
  digest_last_hmac: LAST_HMAC,
  digest_file_id: DIGEST_FILE_ID,
  job_id: JOB_ID,
  started_at: "2026-09-12T16:45:02.000000Z",
  finished_at: "2026-09-12T16:45:09.000000Z",
});
const FAILED = verification({
  id: FAILED_ID,
  trigger: "SCHEDULED",
  to_chain_seq: 9050,
  events_checked: 412,
  result: "FAIL",
  first_failure_seq: 412,
  failure_detail: { reason: "hmac mismatch", chain_seq: 412 },
  digest_last_hmac: null,
  digest_file_id: null,
  started_at: "2026-09-11T02:00:00.000000Z",
  finished_at: "2026-09-11T02:00:04.000000Z",
});

function list(items: readonly unknown[], request?: Request) {
  const counting =
    request !== undefined && new URL(request.url).searchParams.get("count") === "true";
  return HttpResponse.json(
    { items, next_cursor: null },
    { headers: counting ? { "X-Erev-Total-Count": String(items.length) } : {} },
  );
}

const EXPORT_DEFINITION = {
  code: "audit_log_export",
  version: 1,
  name: "Audit log export",
  kind: "EXTRACT",
  description: "Audit events in chain order with every column.",
  parameters_schema: { type: "object", additionalProperties: false, properties: {} },
  output_formats: ["CSV", "JSON"],
  tie_outs: [],
  ipe_logic: null,
};

interface Served {
  /** The searches of `GET /audit-events`, without the paging parameters. */
  readonly events: string[];
  /** The searches of `GET /audit-events/actors`. */
  readonly actors: string[];
  /** The searches of `GET /contracts`. */
  readonly contracts: string[];
  readonly verifyKeys: string[];
  /** The bodies of `POST /saved-views`. */
  readonly savedViews: Record<string, unknown>[];
  /** The searches of the list `GET /audit-events/verifications`. */
  readonly verificationLists: string[];
  /** The ids of `GET /audit-events/verifications/{id}`. */
  readonly verificationIds: string[];
}

interface ServeOptions {
  /** The events of the range the list reads. */
  readonly events?: readonly AuditEvent[];
  /** Events of any age outside that range: answered by their sequence alone. */
  readonly older?: readonly AuditEvent[];
  /** `GET /audit-events?contract_id`: every event that names the contract. */
  readonly trail?: readonly AuditEvent[];
  /** `GET /audit-events/actors`: who acted in the range. */
  readonly actors?: {
    readonly items: readonly AuditEvent["actor"][];
    readonly is_truncated: boolean;
  };
  /** `GET /audit-events/verifications`, newest first; read again on every request. */
  readonly verifications?: () => readonly AuditVerification[];
}

/** The shell's reads and the reads of both screens. */
function serve({
  events = [APPROVED, BOOKED, DENIED],
  older = [],
  trail = [],
  actors = { items: [HANNAH_ACTOR, PRIYA], is_truncated: false },
  verifications = () => [SCHEDULED],
}: ServeOptions = {}): Served {
  const served: Served = {
    events: [],
    actors: [],
    contracts: [],
    verifyKeys: [],
    savedViews: [],
    verificationLists: [],
    verificationIds: [],
  };
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () => list([])),
    http.get(apiUrl("/api/v1/entities"), () => list([])),
    http.get(apiUrl("/api/v1/books"), () => list([])),
    http.get(apiUrl("/api/v1/periods"), () => list([])),
    http.get(apiUrl("/api/v1/saved-views"), () => list([])),
    http.post(apiUrl("/api/v1/saved-views"), async ({ request }) => {
      const body = (await request.json()) as Record<string, unknown>;
      served.savedViews.push(body);
      return HttpResponse.json(
        {
          id: "9b0c1d2e-3f4a-4b5c-8d6e-8f9a0b1c2d3e",
          membership_id: HANNAH.active_membership_id,
          screen_code: body.screen_code,
          name: body.name,
          config: body.config,
          is_shared: false,
          is_favourite: false,
          created_at: "2026-09-12T16:40:00Z",
          updated_at: "2026-09-12T16:40:00Z",
          row_version: 1,
        },
        { status: 201 },
      );
    }),
    http.get(apiUrl("/api/v1/report-definitions/audit_log_export"), () =>
      HttpResponse.json(EXPORT_DEFINITION),
    ),
    http.get(apiUrl("/api/v1/audit-events"), ({ request }) => {
      const params = new URL(request.url).searchParams;
      const paging = new URLSearchParams(params);
      for (const name of ["limit", "cursor", "count"]) {
        paging.delete(name);
      }
      served.events.push(paging.toString());
      // 04 §16.14: a sequence is one event of any age, whatever else the read says.
      const sequence = params.get("chain_seq");
      if (sequence !== null) {
        return list(
          [...events, ...older, ...trail].filter((item) => String(item.chain_seq) === sequence),
          request,
        );
      }
      const outcomes = params.getAll("outcome");
      const types = params.getAll("object_type");
      return list(
        (params.get("contract_id") === CONTRACT_ID ? trail : events).filter(
          (item) =>
            (outcomes.length === 0 || outcomes.includes(item.outcome)) &&
            (types.length === 0 || types.includes(item.object_type)),
        ),
        request,
      );
    }),
    http.get(apiUrl("/api/v1/audit-events/actors"), ({ request }) => {
      served.actors.push(new URL(request.url).searchParams.toString());
      return HttpResponse.json(actors);
    }),
    http.get(apiUrl("/api/v1/audit-events/verifications"), ({ request }) => {
      const params = new URL(request.url).searchParams;
      served.verificationLists.push(params.toString());
      return list(verifications().slice(0, Number(params.get("limit") ?? "50")));
    }),
    http.get(apiUrl("/api/v1/audit-events/verifications/:verificationId"), ({ params }) => {
      const id = String(params.verificationId);
      served.verificationIds.push(id);
      const found = verifications().find((item) => item.id === id);
      return found === undefined
        ? HttpResponse.json(
            { type: "about:blank", title: "Not found", status: 404, code: "not-found" },
            { status: 404, headers: { "Content-Type": "application/problem+json" } },
          )
        : HttpResponse.json(found);
    }),
    http.get(apiUrl("/api/v1/contracts"), ({ request }) => {
      served.contracts.push(new URL(request.url).search);
      return list([
        { id: "aa11bb22-cc33-4d44-8e55-ff6677889900", external_id: "PRJ-CB-2026-010" },
        { id: CONTRACT_ID, external_id: "PRJ-CB-2026-01", contract_no: "C-000042" },
      ]);
    }),
    http.post(apiUrl("/api/v1/audit-events/verify"), ({ request }) => {
      served.verifyKeys.push(request.headers.get("Idempotency-Key") ?? "");
      return HttpResponse.json(job("QUEUED"), {
        status: 202,
        headers: { Location: `/api/v1/jobs/${JOB_ID}` },
      });
    }),
  );
  return served;
}

function job(state: "QUEUED" | "RUNNING" | "SUCCEEDED") {
  return {
    id: JOB_ID,
    kind: "AUDIT_CHAIN_VERIFY",
    state,
    mode: null,
    progress: { done: state === "SUCCEEDED" ? 9112 : 0, total: null },
    result: null,
    problem: null,
    created_by: { id: HANNAH_ID, kind: "USER", display_name: "Hannah Lindqvist" },
    created_at: "2026-09-12T16:45:01Z",
    started_at: state === "QUEUED" ? null : "2026-09-12T16:45:02Z",
    finished_at: state === "SUCCEEDED" ? "2026-09-12T16:45:09Z" : null,
  };
}

function open(entry: string, me = HANNAH) {
  return renderApp(entry, { me, screenRoutes: SCREEN_ROUTES });
}

async function grid(): Promise<HTMLElement> {
  return within(await screen.findByTestId("SF-09-grid-audit-events")).findByRole("grid", {
    name: "Audit events",
  });
}

describe("SF-09:audit-log", () => {
  it("field-level diff", async () => {
    serve();
    // The link names the event by its chain sequence (SCREENS SCR-URL-32 rev 1.20).
    open("/reports/audit-log?drawer=event&event=9104");

    // The drawer opens at once and fills when its event arrives.
    const drawer = await screen.findByRole("complementary", { name: "Event 9,104" });
    expect(screen.getByTestId("SF-09-drawer-event").contains(drawer)).toBe(true);
    expect(await within(drawer).findByText("modification.approve")).toBeTruthy();
    expect(within(drawer).getByText("Succeeded")).toBeTruthy();
    const instant = within(drawer).getByText("10 Sep 2026 15:22:41 UTC");
    expect(instant.tagName).toBe("TIME");
    expect(instant.getAttribute("datetime")).toBe("2026-09-10T15:22:41.318204Z");
    expect(within(drawer).getByText("Priya Raman")).toBeTruthy();

    // The changed fields only, from the event's `diff`: the unchanged memo is not a row.
    const table = within(screen.getByTestId("SF-09-diff")).getByRole("table", {
      name: "Changes (3)",
    });
    const rows = within(table)
      .getAllByRole("row")
      .slice(1)
      .map((row) => Array.from(row.querySelectorAll("th, td"), (cell) => cell.textContent));
    expect(rows).toEqual([
      ["~Changed:", "status", "SUBMITTED", "APPROVED"],
      ["~Changed:", "terms.end_date", "2026-12-31", "2027-06-30"],
      ["+Added:", "client_secret_ref", "—", "[REDACTED]"],
    ]);
    expect(within(table).queryByText("memo")).toBeNull();
    expect(within(table).queryByText("Q3 true-up")).toBeNull();

    // The comment, the detail as recorded (a redacted key stays "[REDACTED]") and the chain values.
    expect(within(drawer).getByText("Agreed with the customer on 08 Sep 2026.")).toBeTruthy();
    expect(within(drawer).getByText(/"authorization": "\[REDACTED\]"/)).toBeTruthy();
    expect(within(drawer).getByText("1a09e4b2…7c21")).toBeTruthy();
    expect(within(drawer).getByText("audit-hmac:1")).toBeTruthy();

    // The grid behind it: newest first as the API answers, outcome chips, the system actor.
    const events = await grid();
    expect(await within(events).findByRole("rowheader", { name: "9,104" })).toBeTruthy();
    const denied = screen.getByTestId("SF-09-row-9090");
    expect(within(denied).getByText("Denied")).toBeTruthy();
    expect(within(denied).getByText("Hannah Lindqvist")).toBeTruthy();
    expect(within(screen.getByTestId("SF-09-row-9097")).getByText("System")).toBeTruthy();
    // The sequence of a row opens that event: the link carries the sequence, never the event's id.
    expect(within(denied).getByRole("link", { name: "9,090" }).getAttribute("href")).toBe(
      "/reports/audit-log?drawer=event&event=9090",
    );

    // Esc inside the drawer closes it and removes its parameters.
    fireEvent.keyDown(within(drawer).getByRole("heading", { name: "Event 9,104" }), {
      key: "Escape",
    });
    await waitFor(() => expect(screen.queryByTestId("SF-09-drawer-event")).toBeNull());
  });

  it("every column holds its header, the two sortable ones with their sort mark", () => {
    expect(
      narrowColumns(
        auditColumns({
          search: "",
          built: new Set(),
          access: accessOf(undefined),
          open: () => undefined,
        }),
      ),
    ).toEqual([]);
  });

  it("a creation and a removal list every leaf of the one document", () => {
    expect(
      eventChanges({
        before: null,
        after: { code: "AVM-US", limits: { amount: "10.00" } },
        diff: null,
      }),
    ).toEqual([
      { id: "0:code", field: "code", kind: "added", current: null, proposed: "AVM-US" },
      {
        id: "1:limits.amount",
        field: "limits.amount",
        kind: "added",
        current: null,
        proposed: "10.00",
      },
    ]);
    expect(eventChanges({ before: { active: true }, after: null, diff: null })).toEqual([
      { id: "0:active", field: "active", kind: "removed", current: "true", proposed: null },
    ]);
    // Without `diff` the two documents are compared leaf by leaf; equal leaves are left out.
    expect(
      eventChanges({
        before: { status: "DRAFT", name: "Standard" },
        after: { status: "ACTIVE", name: "Standard" },
        diff: null,
      }),
    ).toEqual([
      { id: "0:status", field: "status", kind: "changed", current: "DRAFT", proposed: "ACTIVE" },
    ]);
    expect(eventChanges({ before: null, after: null, diff: null })).toEqual([]);
  });

  it("a member that is null before and null after is no change", () => {
    // SCREENS_B §6.3 rev 1.57 (finding Q-58): such a row read "Added".
    expect(
      eventChanges({
        before: null,
        after: null,
        diff: [
          { path: "end_date", before: null, after: null },
          { path: "status", before: "DRAFT", after: "ACTIVE" },
          { path: "memo", after: null },
        ],
      }),
    ).toEqual([
      { id: "1:status", field: "status", kind: "changed", current: "DRAFT", proposed: "ACTIVE" },
    ]);
    // Without `diff`: a leaf null on both sides, and a leaf null on one side and absent on the other.
    expect(
      eventChanges({
        before: { end_date: null, memo: null, status: "DRAFT" },
        after: { end_date: null, status: "ACTIVE" },
        diff: null,
      }),
    ).toEqual([
      { id: "0:status", field: "status", kind: "changed", current: "DRAFT", proposed: "ACTIVE" },
    ]);
    // A creation and a removal list the leaves that hold a value.
    expect(
      eventChanges({ before: null, after: { code: "AVM-US", memo: null }, diff: null }),
    ).toEqual([{ id: "0:code", field: "code", kind: "added", current: null, proposed: "AVM-US" }]);
    expect(
      eventChanges({ before: { code: "AVM-US", memo: null }, after: null, diff: null }),
    ).toEqual([
      { id: "0:code", field: "code", kind: "removed", current: "AVM-US", proposed: null },
    ]);
  });

  it("verify chain now", async () => {
    let verified = false;
    let finish: (() => void) | undefined;
    const running = new Promise<void>((resolve) => {
      finish = resolve;
    });
    const served = serve({
      verifications: () => (verified ? [ON_DEMAND, SCHEDULED] : [SCHEDULED]),
    });
    server.use(
      http.get(apiUrl("/api/v1/jobs/:jobId"), async () => {
        await running;
        verified = true;
        return HttpResponse.json(job("SUCCEEDED"));
      }),
      http.get(apiUrl(`/api/v1/files/${DIGEST_FILE_ID}`), () => HttpResponse.json({})),
    );
    const { router } = open("/reports/audit-log");

    const header = await screen.findByTestId("SF-09-banner-chain");
    expect(
      await within(header).findByRole("link", {
        name: "Audit chain verified 12 Sep 2026 02:00 UTC · 9,050 events",
      }),
    ).toBeTruthy();
    expect(within(header).getByText("Verified")).toBeTruthy();

    fireEvent.click(within(header).getByRole("button", { name: "Verify chain now" }));
    // DS-CMP-24: the job shows in the header while it runs.
    expect(
      await within(header).findByRole("progressbar", { name: "Verifying the audit chain" }),
    ).toBeTruthy();
    expect(served.verifyKeys).toHaveLength(1);
    expect(served.verifyKeys[0]).toMatch(/^[0-9a-f-]{36}$/);

    finish?.();
    // SCREENS_B §6.3: the toast with the events checked and the last chain value, and the header.
    expect(
      await screen.findByText("Audit chain verified: 9,112 events, last chain value 1a09e4b2."),
    ).toBeTruthy();
    const link = await within(header).findByRole("link", {
      name: "Audit chain verified 12 Sep 2026 16:45 UTC · 9,112 events",
    });
    expect(link.getAttribute("href")).toBe(`/reports/audit-log/verifications/${ON_DEMAND_ID}`);
    expect(within(header).getByText("Verified")).toBeTruthy();
    expect(within(header).queryByRole("progressbar")).toBeNull();

    // "View details" opens SF-09:verification: the chip, the figures and the digest download.
    fireEvent.click(screen.getByRole("button", { name: "View details" }));
    await waitFor(() =>
      expect(router.state.location.pathname).toBe(
        `/reports/audit-log/verifications/${ON_DEMAND_ID}`,
      ),
    );
    expect(
      await screen.findByRole("heading", { level: 1, name: "Audit chain verification" }),
    ).toBeTruthy();
    const strip = await screen.findByTestId("SF-09-kpi-strip");
    const figures = Array.from(strip.querySelectorAll("dt")).map((term) => [
      term.textContent,
      term.nextElementSibling?.textContent,
    ]);
    expect(figures).toEqual([
      ["Events checked", "9,112"],
      ["First failure", "—"],
      ["Last chain value", "1a09e4b2…7c21"],
    ]);
    expect(screen.getByText("On demand", { selector: "dd" })).toBeTruthy();
    expect(screen.getByText("12 Sep 2026 16:45:02 UTC")).toBeTruthy();
    expect(screen.getByText("1 to 9,112")).toBeTruthy();
    const digest = screen.getByRole("link", { name: "Download digest" });
    expect(digest.getAttribute("href")).toBe(`/api/v1/files/${DIGEST_FILE_ID}/content`);
    expect(digest.hasAttribute("download")).toBe(true);

    // Recent verifications: the current one is not a link; the other links to its record.
    const recent = await screen.findByTestId("SF-09-grid-verifications");
    const lines = within(recent)
      .getAllByRole("row")
      .slice(1)
      .map((row) =>
        within(row)
          .getAllByRole("cell")
          .map((cell) => cell.textContent),
      );
    expect(lines).toEqual([
      ["12 Sep 2026 16:45 UTC", "On demand", "Verified", "9,112", "—No value"],
      ["12 Sep 2026 02:00 UTC", "Scheduled", "Verified", "9,050", "—No value"],
    ]);
    expect(
      within(recent).getByRole("link", { name: "12 Sep 2026 02:00 UTC" }).getAttribute("href"),
    ).toBe(`/reports/audit-log/verifications/${SCHEDULED_ID}`);
    expect(within(recent).queryByRole("link", { name: "12 Sep 2026 16:45 UTC" })).toBeNull();
  });

  it("reads a stated range: the last 30 days by default, the Occurred chip otherwise", async () => {
    const served = serve();
    const { router } = open("/reports/audit-log");
    await grid();
    await waitFor(() => expect(served.events).toHaveLength(1));
    // 13 Aug 2026 00:00 UTC inclusive to 13 Sep 2026 00:00 UTC exclusive; no chip reaches the URL.
    expect(served.events[0]).toBe("from=2026-08-13T00%3A00%3A00Z&to=2026-09-13T00%3A00%3A00Z");
    expect(router.state.location.search).toBe("");
    expect(
      screen.getByText(
        "Showing the last 30 days, 13 Aug 2026 – 12 Sep 2026 (UTC). Add the Occurred filter to read another range.",
      ),
    ).toBeTruthy();
    // SCR-IA-02: the Reports tabs of the built pages the Auditor may read.
    const tabs = screen.getByRole("navigation", { name: "Reports sections" });
    expect(
      within(tabs)
        .getAllByRole("link")
        .map((tab) => [tab.textContent, tab.getAttribute("aria-current")]),
    ).toEqual([
      ["Catalogue", null],
      ["Report runs", null],
      ["Audit log", "page"],
    ]);

    await router.navigate(
      "/reports/audit-log?f.action=is:contract.book&f.occurred=between:2026-09-01,2026-09-10",
    );
    await waitFor(() => expect(served.events).toHaveLength(2));
    expect(served.events[1]).toBe(
      "action=contract.book&from=2026-09-01T00%3A00%3A00Z&to=2026-09-11T00%3A00%3A00Z",
    );
    expect(screen.queryByText(/^Showing the last 30 days/)).toBeNull();
    expect(
      screen.getByRole("button", {
        name: "Occurred between 01 Sep 2026 and 10 Sep 2026, edit filter",
      }),
    ).toBeTruthy();
  });

  it("the object filter lists the trail of a contract, read whole", async () => {
    // 04 §16.14: every event that names the contract, whatever its object type.
    const served = serve({
      trail: [
        event({ ...APPROVED, detail: { contract_id: CONTRACT_ID }, object_label: "MOD-000007" }),
        event({ ...BOOKED, object_label: "PRJ-CB-2026-01" }),
      ],
    });
    const { router } = open("/reports/audit-log?f.object=is:PRJ-CB-2026-01");
    const events = await grid();
    expect(await within(events).findByRole("rowheader", { name: "9,097" })).toBeTruthy();
    // The contract search, then the trail by the contract's id: no object type, and no range.
    expect(served.contracts).toEqual(["?q=PRJ-CB-2026-01&limit=50"]);
    expect(served.events).toEqual([`contract_id=${CONTRACT_ID}`]);
    // The approval of the modification is an event of the contract's trail.
    expect(within(screen.getByTestId("SF-09-row-9104")).getByText("MOD-000007")).toBeTruthy();
    expect(
      screen.getByText(
        "Showing every event that names PRJ-CB-2026-01. Add the Occurred filter to narrow the range.",
      ),
    ).toBeTruthy();
    expect(screen.queryByText(/^Showing the last 30 days/)).toBeNull();
    // The names of the Actor filter are those of the API's own range: the screen sends none.
    expect(served.actors).toEqual([""]);

    // The object type narrows the trail; the Occurred chip gives it a range.
    await router.navigate(
      "/reports/audit-log?f.object=is:PRJ-CB-2026-01&f.object_type=is:Modification&f.occurred=between:2026-09-01,2026-09-10",
    );
    await waitFor(() => expect(served.events).toHaveLength(2));
    expect(served.events[1]).toBe(
      `object_type=modification&contract_id=${CONTRACT_ID}&from=2026-09-01T00%3A00%3A00Z&to=2026-09-11T00%3A00%3A00Z`,
    );
    await waitFor(() => expect(screen.queryByTestId("SF-09-row-9097")).toBeNull());
    expect(screen.getByTestId("SF-09-row-9104")).toBeTruthy();
    expect(screen.queryByText(/^Showing every event that names/)).toBeNull();
  });

  it("the Outcome chip filters the list by outcome", async () => {
    const served = serve();
    const { router } = open("/reports/audit-log?f.outcome=in:DENIED,FAILED");
    await grid();
    expect(await screen.findByTestId("SF-09-row-9090")).toBeTruthy();
    // One `outcome` per literal: the API answers any of them.
    expect(served.events).toEqual([
      "outcome=DENIED&outcome=FAILED&from=2026-08-13T00%3A00%3A00Z&to=2026-09-13T00%3A00%3A00Z",
    ]);
    expect(screen.queryByTestId("SF-09-row-9104")).toBeNull();
    const bar = screen.getByRole("toolbar", { name: "Filters" });
    expect(
      within(bar).getByRole("button", { name: "Outcome is Denied or Failed, edit filter" }),
    ).toBeTruthy();

    // The editor offers the three outcomes of E-81 by their chip words.
    await router.navigate("/reports/audit-log");
    await screen.findByTestId("SF-09-row-9104");
    fireEvent.click(within(bar).getByRole("button", { name: "Filter" }));
    fireEvent.click(
      within(screen.getByRole("dialog", { name: "Filter" })).getByRole("button", {
        name: "Outcome",
      }),
    );
    const editor = screen.getByRole("dialog", { name: "Outcome filter" });
    expect(
      within(editor)
        .getAllByRole("checkbox")
        .map((box) => box.closest("label")?.textContent),
    ).toEqual(["Succeeded", "Denied", "Failed"]);
    fireEvent.click(within(editor).getByRole("checkbox", { name: "Denied" }));
    fireEvent.click(within(editor).getByRole("button", { name: "Apply" }));
    await waitFor(() => expect(router.state.location.search).toBe("?f.outcome=is:DENIED"));
    await waitFor(() =>
      expect(served.events.at(-1)).toBe(
        "outcome=DENIED&from=2026-08-13T00%3A00%3A00Z&to=2026-09-13T00%3A00%3A00Z",
      ),
    );
  });

  it("the filters in route order: Object, Object type, Actor, Action, Outcome, Occurred", () => {
    const names = (permissions: string[]) =>
      auditFilterFields("2026-09-12", [], accessOf(signedInMe({ permissions }))).map(
        (field) => field.name,
      );
    expect(names(["contract.read"])).toEqual([
      "object",
      "object_type",
      "actor",
      "action",
      "outcome",
      "occurred",
    ]);
    // The object filter names a contract through the contract search.
    expect(names([])).toEqual(["object_type", "actor", "action", "outcome", "occurred"]);
  });

  it("the Object cell shows the business label, linked where the record has a screen", async () => {
    serve({
      events: [
        // A contract by its external id: an identifier, linked to the record.
        event({ ...BOOKED, object_label: "PRJ-CB-2026-01" }),
        // A modification has no screen that opens from its id: the label is text.
        event({ ...APPROVED, object_label: "MOD-000007" }),
        // A membership is labelled by the person's name: the text face, not the identifier face.
        event({
          ...DENIED,
          action: "role_assignment.create",
          object_type: "tenant_membership",
          object_id: MAYA_MEMBERSHIP,
          object_label: "Maya Chen",
        }),
        // No label — a row the reader's access does not show, or a type without one: the type in
        // words, linked where the type has a screen, and nothing that says a label exists.
        event({ ...BOOKED, id: "6b5a4f3e-2d1c-4e7d-8c8f-7e0d9c8b7a6f", chain_seq: 9096 }),
        event({ ...APPROVED, id: "7c6b5a4f-3e2d-4f8e-9d9a-8f1e0d9c8b7a", chain_seq: 9103 }),
      ],
    });
    open("/reports/audit-log?drawer=event&event=9104");
    await grid();
    const cell = (sequence: number) =>
      screen.getByTestId(`SF-09-row-${String(sequence)}`).querySelector('[data-column="object"]');

    const contract = within(await screen.findByTestId("SF-09-row-9097")).getByRole("link", {
      name: "PRJ-CB-2026-01",
    });
    expect(contract.getAttribute("href")).toBe(`/contracts/${CONTRACT_ID}`);
    expect(contract.className).toContain("font-mono");
    expect(cell(9097)?.textContent).toBe("PRJ-CB-2026-01");

    const modification = within(screen.getByTestId("SF-09-row-9104")).getByText("MOD-000007");
    expect(modification.closest("a")).toBeNull();
    expect(modification.className).toContain("font-mono");

    const member = within(screen.getByTestId("SF-09-row-9090")).getByText("Maya Chen");
    expect(member.closest("a")).toBeNull();
    expect(member.className).not.toContain("font-mono");

    const hidden = within(screen.getByTestId("SF-09-row-9096")).getByRole("link", {
      name: "Contract",
    });
    expect(hidden.getAttribute("href")).toBe(`/contracts/${CONTRACT_ID}`);
    expect(hidden.className).not.toContain("font-mono");
    expect(cell(9096)?.textContent).toBe("Contract");
    expect(cell(9103)?.textContent).toBe("—No value");
    for (const sequence of [9096, 9103]) {
      expect(screen.getByTestId(`SF-09-row-${String(sequence)}`).textContent).not.toMatch(
        /label|hidden|restricted/i,
      );
    }

    // The drawer names the object by its type in words and its label.
    const drawer = await screen.findByRole("complementary", { name: "Event 9,104" });
    const object = Array.from(drawer.querySelectorAll("dt")).find(
      (term) => term.textContent === "Object",
    )?.nextElementSibling;
    expect(object?.textContent).toBe("ModificationMOD-000007");
  });

  it("Enter on the Object or Actor cell opens its link, and the event where it shows none", () => {
    const opened: string[] = [];
    const columns = auditColumns({
      search: "?f.action=is:contract.book",
      built: new Set(["/contracts/:contractId", "/settings/users/:membershipId"]),
      access: accessOf(signedInMe({ permissions: ["audit.read", "contract.read", "user.manage"] })),
      open: (to) => opened.push(to),
    });
    const column = (id: string) => columns.find((item) => item.id === id);
    const drawer = "/reports/audit-log?f.action=is:contract.book&drawer=event&event=";

    column("object")?.activate?.(BOOKED);
    column("object")?.activate?.(APPROVED);
    column("actor")?.activate?.(event({ ...APPROVED, actor_membership_id: PRIYA_MEMBERSHIP }));
    column("actor")?.activate?.(BOOKED);
    expect(opened).toEqual([
      `/contracts/${CONTRACT_ID}`,
      `${drawer}9104`,
      `/settings/users/${PRIYA_MEMBERSHIP}`,
      `${drawer}9097`,
    ]);
  });

  it("the Actor links to the user screen for a holder of user.manage", async () => {
    const events = [
      event({ ...APPROVED, actor_membership_id: PRIYA_MEMBERSHIP }),
      // The system, an API client and an operator carry no membership.
      BOOKED,
      BY_CLIENT,
    ];
    serve({ events });
    const admin = signedInMe({
      user: HANNAH.user,
      permissions: [...HANNAH.permissions, "user.read", "user.manage"],
    });
    open("/reports/audit-log?drawer=event&event=9104", admin);
    await grid();
    const row = await screen.findByTestId("SF-09-row-9104");
    expect(within(row).getByRole("link", { name: "Priya Raman" }).getAttribute("href")).toBe(
      `/settings/users/${PRIYA_MEMBERSHIP}`,
    );
    expect(
      within(screen.getByTestId("SF-09-row-9097")).getByText("System").closest("a"),
    ).toBeNull();
    expect(
      within(screen.getByTestId("SF-09-row-9080")).getByText("Billing sync").closest("a"),
    ).toBeNull();
    const drawer = await screen.findByRole("complementary", { name: "Event 9,104" });
    expect(within(drawer).getByRole("link", { name: "Priya Raman" }).getAttribute("href")).toBe(
      `/settings/users/${PRIYA_MEMBERSHIP}`,
    );

    // Without `user.manage` the name is text: the user screen would refuse the reader.
    cleanup();
    serve({ events });
    open("/reports/audit-log?drawer=event&event=9104");
    await grid();
    const plain = within(await screen.findByTestId("SF-09-row-9104")).getByText("Priya Raman");
    expect(plain.closest("a")).toBeNull();
    const text = await screen.findByRole("complementary", { name: "Event 9,104" });
    expect(within(text).queryByRole("link", { name: "Priya Raman" })).toBeNull();
    expect(within(text).getByText("Priya Raman")).toBeTruthy();
  });

  it("the Actor filter offers who acted in the range on screen", async () => {
    const served = serve({
      actors: {
        items: [
          { id: CLIENT_ID, kind: "API_CLIENT", display_name: "Billing sync" },
          { id: OPERATOR_ID, kind: "OPERATOR", display_name: "Dana Whitfield" },
          HANNAH_ACTOR,
          PRIYA,
        ],
        is_truncated: false,
      },
    });
    // Maya did nothing in the range: the chip of the link is kept under a name that says so.
    const { router } = open(`/reports/audit-log?f.actor=is:${MAYA_ID}`);
    await grid();
    await waitFor(() => expect(served.actors).toHaveLength(1));
    // The names are read over the range the list is read over.
    expect(served.actors[0]).toBe("from=2026-08-13T00%3A00%3A00Z&to=2026-09-13T00%3A00%3A00Z");
    const bar = screen.getByRole("toolbar", { name: "Filters" });
    expect(
      await within(bar).findByRole("button", { name: "Actor is another member, edit filter" }),
    ).toBeTruthy();
    await waitFor(() =>
      expect(served.events.at(-1)).toBe(
        `actor_id=${MAYA_ID}&from=2026-08-13T00%3A00%3A00Z&to=2026-09-13T00%3A00%3A00Z`,
      ),
    );
    // The link's chip survives the load of the names (SCR-URL-21 would drop an unknown value).
    expect(router.state.location.search).toBe(`?f.actor=is:${MAYA_ID}`);

    // The editor: every principal of the range by the name the Actor column gives it; the viewer,
    // who did nothing in the range, is not among them.
    await router.navigate("/reports/audit-log?f.occurred=between:2026-09-01,2026-09-10");
    await waitFor(() => expect(served.actors).toHaveLength(2));
    expect(served.actors[1]).toBe("from=2026-09-01T00%3A00%3A00Z&to=2026-09-11T00%3A00%3A00Z");
    fireEvent.click(within(bar).getByRole("button", { name: "Filter" }));
    fireEvent.click(
      within(screen.getByRole("dialog", { name: "Filter" })).getByRole("button", { name: "Actor" }),
    );
    const editor = screen.getByRole("dialog", { name: "Actor filter" });
    await waitFor(() =>
      expect(
        within(editor)
          .getAllByRole("checkbox")
          .map((box) => box.closest("label")?.textContent),
      ).toEqual([
        "Billing sync",
        "Hannah Lindqvist",
        "Operator Dana Whitfield under support grant",
        "Priya Raman",
      ]),
    );
    expect(screen.queryByText(/^Actor filter: showing the first/)).toBeNull();
  });

  it("more actors than the API answers: the screen says the names are the first of the range", async () => {
    serve({ actors: { items: [HANNAH_ACTOR, PRIYA], is_truncated: true } });
    open("/reports/audit-log");
    await grid();
    expect(
      await screen.findByText("Actor filter: showing the first 2 who acted in this range."),
    ).toBeTruthy();
  });

  it("the options of the Actor filter", () => {
    expect(
      actorOptions(
        [PRIYA, { id: null, kind: "SYSTEM", display_name: "System" }, HANNAH_ACTOR],
        null,
      ),
    ).toEqual([
      { value: HANNAH_ID, label: "Hannah Lindqvist" },
      { value: PRIYA_ID, label: "Priya Raman" },
    ]);
    // A linked actor of the range keeps its name; one outside it is "another member".
    expect(actorOptions([PRIYA], PRIYA_ID)).toEqual([{ value: PRIYA_ID, label: "Priya Raman" }]);
    expect(actorOptions([PRIYA], MAYA_ID)).toEqual([
      { value: PRIYA_ID, label: "Priya Raman" },
      { value: MAYA_ID, label: "another member" },
    ]);
  });

  it("Export is not offered with a filter the report does not take", async () => {
    // RPT-43 takes neither an outcome nor the trail of a contract: its rows would not be the list's.
    serve({ trail: [BOOKED] });
    const { router } = open("/reports/audit-log?f.outcome=is:DENIED");
    await grid();
    const unavailable = await screen.findByRole("button", { name: "Export" });
    expect(unavailable.getAttribute("aria-disabled")).toBe("true");
    expect(unavailable.getAttribute("aria-haspopup")).toBeNull();
    fireEvent.focus(unavailable);
    expect(
      await screen.findByText(
        "The export cannot apply the Object or Outcome filter. Remove that filter to export.",
      ),
    ).toBeTruthy();

    await router.navigate("/reports/audit-log?f.object=is:PRJ-CB-2026-01");
    await screen.findByTestId("SF-09-row-9097");
    expect(screen.getByRole("button", { name: "Export" }).getAttribute("aria-disabled")).toBe(
      "true",
    );

    // Every other filter is a parameter of the run: the menu is offered.
    await router.navigate("/reports/audit-log?f.action=is:contract.book");
    await waitFor(() =>
      expect(screen.getByRole("button", { name: "Export" }).getAttribute("aria-haspopup")).toBe(
        "menu",
      ),
    );
    expect(screen.getByRole("button", { name: "Export" }).getAttribute("aria-disabled")).toBeNull();
  });

  it("an event on a report run links to the run record", async () => {
    // SCREENS_B §6.3 rev 1.53: a report run joins the objects whose record opens from the id.
    serve({ events: [APPROVED, FOR_MAYA_ON_RUN] });
    open("/reports/audit-log");
    await grid();
    const row = await screen.findByTestId("SF-09-row-9061");
    expect(within(row).getByRole("link", { name: "Report run" }).getAttribute("href")).toBe(
      `/reports/runs/${REPORT_RUN_ID}`,
    );
  });

  it("an object without a screen shows its type and no link", async () => {
    serve();
    open("/reports/audit-log");
    await grid();
    const row = await screen.findByTestId("SF-09-row-9104");
    expect(within(row).getByText("Modification")).toBeTruthy();
    expect(within(row).getAllByRole("link")).toHaveLength(1);
    expect(within(row).queryByText(MODIFICATION_ID)).toBeNull();
  });

  // Item AUD-ACTOR-BIND-1 (SCREENS_B §6.3 rev 1.45): the three bindings to API-S-Actor.
  it("an API client is named by its name", async () => {
    serve({ events: [APPROVED, BY_CLIENT] });
    open("/reports/audit-log");
    await grid();
    const row = await screen.findByTestId("SF-09-row-9080");
    expect(within(row).getByText("Billing sync")).toBeTruthy();
    expect(within(row).queryByText("API client")).toBeNull();
    // The client's id stays a recorded value and never stands for the name.
    expect(within(row).queryByText(CLIENT_ID)).toBeNull();
  });

  it('an operator reads "Operator <name> under support grant"', async () => {
    serve({ events: [APPROVED, BY_OPERATOR] });
    open("/reports/audit-log?drawer=event&event=9070");
    const drawer = await screen.findByRole("complementary", { name: "Event 9,070" });
    expect(
      await within(drawer).findByText("Operator Dana Whitfield under support grant"),
    ).toBeTruthy();
    await grid();
    const row = await screen.findByTestId("SF-09-row-9070");
    expect(within(row).getByText("Operator Dana Whitfield under support grant")).toBeTruthy();
  });

  it('"On behalf of" names the principal a step acted for', async () => {
    serve({ events: [APPROVED, FOR_MAYA, FOR_CLIENT] });
    open("/reports/audit-log?drawer=event&event=9060");
    const events = await grid();
    expect(within(events).getByRole("columnheader", { name: "On behalf of" })).toBeTruthy();
    // A member and an API client by name, in the row of the system step that acted for them.
    const forMaya = await screen.findByTestId("SF-09-row-9060");
    expect(within(forMaya).getByText("System")).toBeTruthy();
    expect(within(forMaya).getByText("Maya Chen")).toBeTruthy();
    expect(within(screen.getByTestId("SF-09-row-9050")).getByText("Billing sync")).toBeTruthy();
    // An event that names nobody shows no value in the column: Priya Raman acted for herself.
    const own = screen.getByTestId("SF-09-row-9104");
    expect(within(own).getAllByText("Priya Raman")).toHaveLength(1);
    // The drawer names the principal after the actor; the recorded id stays among the recorded values.
    const drawer = await screen.findByRole("complementary", { name: "Event 9,060" });
    const definition = (term: string) =>
      Array.from(drawer.querySelectorAll("dt")).find((item) => item.textContent === term)
        ?.nextElementSibling;
    expect(definition("On behalf of")?.textContent).toBe("Maya Chen");
    // DS-FMT-23: the id as its first 8 and last 4 characters.
    expect(
      within(definition("On behalf of (id)") as HTMLElement).getByText("4b3a2f1e…b4a3"),
    ).toBeTruthy();
  });

  it("a saved view stored from the default state holds no dates", async () => {
    const served = serve();
    const { router } = open("/reports/audit-log");
    await grid();
    fireEvent.click(await screen.findByRole("button", { name: "View: All events" }));
    fireEvent.click(
      within(screen.getByRole("menu", { name: "Views" })).getByRole("menuitem", {
        name: "Save as new view",
      }),
    );
    const dialog = screen.getByRole("dialog", { name: "Save as new view" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Name/ }), {
      target: { value: "Recent events" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Save view" }));
    await waitFor(() => expect(served.savedViews).toHaveLength(1));
    const [stored] = served.savedViews;
    expect(stored?.screen_code).toBe("SF-09:audit-log");
    // The default range is not a filter: the view stores none, so it stays "the last 30 days".
    expect((stored?.config as { readonly filters: unknown }).filters).toEqual({});
    expect(JSON.stringify(stored)).not.toMatch(/\d{4}-\d{2}-\d{2}/);
    expect(new URLSearchParams(router.state.location.search).has("f.occurred")).toBe(false);
  });

  it("an object id no contract has lists nothing and says why", async () => {
    const served = serve();
    open("/reports/audit-log?f.object=is:NO-SUCH-ID");
    expect(
      await screen.findByRole("heading", { name: "No audit events match these filters" }),
    ).toBeTruthy();
    expect(screen.getByText("No contract has the external id or number NO-SUCH-ID.")).toBeTruthy();
    expect(served.events).toEqual([]);
  });

  it("a link to a sequence the loaded rows do not hold reads that event alone", async () => {
    // "Open event 412" of a failed verification: an event of March, and a list filtered to other rows.
    const served = serve({ older: [OLD] });
    const { router } = open(
      `/reports/audit-log?f.action=is:contract.book&drawer=event&event=${String(OLD_SEQUENCE)}`,
    );
    const drawer = await screen.findByRole("complementary", { name: "Event 412" });
    expect(await within(drawer).findByText("role.update")).toBeTruthy();
    expect(within(drawer).getByText("02 Mar 2026 08:15:00 UTC")).toBeTruthy();
    // One event by its sequence: no range and none of the list's filters.
    expect(served.events).toContain("chain_seq=412");
    await grid();
    expect(screen.queryByTestId("SF-09-row-412")).toBeNull();
    expect(router.state.location.search).toBe("?f.action=is:contract.book&drawer=event&event=412");
    expect(screen.queryByText("The link names no audit event of this workspace.")).toBeNull();

    // Esc closes the drawer and removes its parameters; the filter stays.
    fireEvent.keyDown(within(drawer).getByRole("heading", { name: "Event 412" }), {
      key: "Escape",
    });
    await waitFor(() => expect(screen.queryByTestId("SF-09-drawer-event")).toBeNull());
    expect(router.state.location.search).toBe("?f.action=is:contract.book");
  });

  it("an event the loaded rows hold opens without a read of its own", async () => {
    const served = serve();
    const { router } = open("/reports/audit-log");
    await grid();
    await screen.findByTestId("SF-09-row-9090");
    await router.navigate("/reports/audit-log?drawer=event&event=9090");
    expect(await screen.findByRole("complementary", { name: "Event 9,090" })).toBeTruthy();
    expect(served.events.filter((search) => search.includes("chain_seq"))).toEqual([]);
  });

  it("the banner of an unknown event goes when an event opens", async () => {
    serve();
    const { router } = open("/reports/audit-log?drawer=event&event=77001");
    await grid();
    const banner = await screen.findByText("The link names no audit event of this workspace.");
    await screen.findByTestId("SF-09-row-9090");
    await router.navigate("/reports/audit-log?drawer=event&event=9090");
    expect(await screen.findByRole("complementary", { name: "Event 9,090" })).toBeTruthy();
    await waitFor(() => expect(banner.isConnected).toBe(false));
  });

  it("the read of one event that fails shows in the drawer with Retry", async () => {
    const served = serve({ older: [OLD] });
    let failing = true;
    server.use(
      http.get(apiUrl("/api/v1/audit-events"), ({ request }) => {
        if (failing && new URL(request.url).searchParams.has("chain_seq")) {
          return HttpResponse.json(
            { type: "about:blank", title: "The service is unavailable", status: 503 },
            { status: 503, headers: { "Content-Type": "application/problem+json" } },
          );
        }
        return undefined;
      }),
    );
    open("/reports/audit-log?drawer=event&event=412");
    const drawer = await screen.findByRole("complementary", { name: "Event 412" });
    expect(
      await within(drawer).findByRole("heading", { name: "Could not load the event" }),
    ).toBeTruthy();
    expect(within(drawer).getByText("The service is unavailable")).toBeTruthy();
    failing = false;
    fireEvent.click(within(drawer).getByRole("button", { name: "Retry" }));
    // The same panel fills with the event.
    expect(await within(drawer).findByText("role.update")).toBeTruthy();
    expect(within(drawer).queryByRole("heading", { name: "Could not load the event" })).toBeNull();
    expect(served.events).toContain("chain_seq=412");
  });

  it.each([
    // A sequence the workspace does not hold: the read by sequence answers nothing.
    ["a sequence no event has", "77001", ["chain_seq=77001"]],
    // The id of a loaded event: an id is not a sequence, names no event and is not sent.
    ["an event id", EVENT_APPROVE, []],
    ["a number a sequence cannot be", "0412", []],
  ])("a link to %s closes the drawer and says so", async (_case, value, reads) => {
    const served = serve();
    const { router } = open(`/reports/audit-log?drawer=event&event=${value}`);
    await grid();
    expect(
      await screen.findByText("The link names no audit event of this workspace."),
    ).toBeTruthy();
    expect(router.state.location.search).toBe("");
    expect(screen.queryByTestId("SF-09-drawer-event")).toBeNull();
    expect(served.events.filter((search) => search.includes("chain_seq"))).toEqual(reads);
  });

  it("without audit.read the screen is access-limited and reads nothing", async () => {
    const served = serve();
    open("/reports/audit-log", signedInMe({ permissions: ["contract.read", "report.run"] }));
    expect(
      await screen.findByRole("heading", { name: "You do not have access to the audit log" }),
    ).toBeTruthy();
    expect(accessDescription()).toBe(
      "Ask a workspace administrator for a role that includes viewing the audit log (audit.read).",
    );
    expect(served.events).toEqual([]);
  });

  // SCREENS_B §6.3 (rev 1.68) and SCREENS §0.6 SCR-PERM-01, SCR-PERM-02 (item W-12, slice b; supervisor
  // ruling R-28): the audit log is a list of the whole workspace, read with `audit.read` for all entities.
  it("a holder of audit.read for named entities is told that the log covers every entity, and nothing is read", async () => {
    const served = serve();
    const held = ["contract.read", "report.run", "audit.read"];
    open(
      "/reports/audit-log",
      signedInMe({
        permissions: held,
        permission_scopes: Object.fromEntries(
          held.map((code) => [code, ["0a1b2c3d-4e5f-4a6b-8c7d-000000000003"]]),
        ),
      }),
    );

    expect(
      await screen.findByRole("heading", { name: "You do not have access to the audit log" }),
    ).toBeTruthy();
    expect(accessDescription()).toBe(
      "The audit log covers every entity of the workspace. Ask a workspace administrator for a role that includes viewing the audit log (audit.read) for all entities.",
    );
    expect(served.events).toEqual([]);
    expect(served.actors).toEqual([]);
  });

  it("a read of the audit events that is refused renders the access-limited state in place of the page", async () => {
    serve();
    const refused: string[] = [];
    server.use(
      http.get(apiUrl("/api/v1/audit-events"), ({ request }) => {
        refused.push(new URL(request.url).search);
        return problemResponse("forbidden", 403, "Permission denied");
      }),
    );
    open("/reports/audit-log");

    expect(
      await screen.findByRole("heading", { name: "You do not have access to the audit log" }),
    ).toBeTruthy();
    expect(accessDescription()).toBe(
      "The audit log covers every entity of the workspace. Ask a workspace administrator for a role that includes viewing the audit log (audit.read) for all entities.",
    );
    // The page is gone with its commands and its error state.
    expect(screen.queryByTestId("SF-09-grid-audit-events")).toBeNull();
    expect(screen.queryByRole("button", { name: "Verify chain now" })).toBeNull();
    expect(screen.queryByText("Could not load audit events")).toBeNull();
    expect(screen.queryByText("Permission denied")).toBeNull();
    // The refused read is not sent again.
    expect(refused).toHaveLength(1);
  });
});

describe("SF-09:verification", () => {
  it("a failed verification shows the banner and the failure detail", async () => {
    const served = serve({ verifications: () => [SCHEDULED, FAILED] });
    open(`/reports/audit-log/verifications/${FAILED_ID}`);
    expect(
      await screen.findByRole("heading", { level: 1, name: "Audit chain verification" }),
    ).toBeTruthy();
    const banner = await screen.findByTestId("SF-09-banner-verification-failed");
    expect(
      within(banner).getByRole("heading", {
        name: "Audit chain verification failed at event 412",
      }),
    ).toBeTruthy();
    expect(
      within(banner).getByText("Open the verification details and follow the runbook."),
    ).toBeTruthy();
    // DS-CMP-29: present on load, so not an alert.
    expect(within(banner).queryByRole("alert")).toBeNull();
    // The first failing event opens in the audit log by its sequence (SCREENS_B §6.4 rev 1.45).
    expect(within(banner).getByRole("link", { name: "Open event 412" }).getAttribute("href")).toBe(
      "/reports/audit-log?drawer=event&event=412",
    );
    // The E-98 chip of the record, in the region the `h1` names.
    const record = screen.getByRole("region", { name: "Audit chain verification" });
    expect(within(record).getByText("Verification failed")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Download digest" })).toBeNull();
    const detail = screen.getByRole("table", { name: "Failure detail" });
    expect(
      within(detail)
        .getAllByRole("row")
        .slice(1)
        .map((row) => row.textContent),
    ).toEqual(["chain_seq412", "reasonhmac mismatch"]);
    // SCREENS_B §6.4 rev 1.57: the run is read by its id; the list is read for the recent ten only.
    expect(served.verificationIds).toEqual([FAILED_ID]);
    await screen.findByTestId("SF-09-grid-verifications");
    expect(served.verificationLists).toEqual(["limit=10"]);
  });

  it("an id the workspace does not hold is not found", async () => {
    const served = serve();
    const unknown = "00000000-0000-4000-8000-000000000000";
    const { router } = open(`/reports/audit-log/verifications/${unknown}`);
    expect(await screen.findByRole("heading", { name: "Verification not found" })).toBeTruthy();
    // One read by id (404); no page of the list is read to look for it.
    expect(served.verificationIds).toEqual([unknown]);
    expect(served.verificationLists.filter((search) => search !== "limit=10")).toEqual([]);
    fireEvent.click(screen.getByRole("button", { name: "Go to the audit log" }));
    await waitFor(() => expect(router.state.location.pathname).toBe("/reports/audit-log"));
  });

  // SCREENS_B §6.4 (rev 1.68; SCREENS §0.6 SCR-PERM-02): a refusal is not an error with "Retry".
  it("a read of the verification that is refused renders the access-limited state and is not sent again", async () => {
    serve();
    const refused: string[] = [];
    server.use(
      http.get(apiUrl("/api/v1/audit-events/verifications/:verificationId"), ({ request }) => {
        refused.push(new URL(request.url).pathname);
        return problemResponse("forbidden", 403, "Permission denied");
      }),
    );
    const { queryClient } = open(`/reports/audit-log/verifications/${FAILED_ID}`);

    expect(
      await screen.findByRole("heading", { name: "You do not have access to the audit log" }),
    ).toBeTruthy();
    expect(screen.queryByText("Could not load the verification")).toBeNull();
    expect(screen.queryByRole("button", { name: "Retry" })).toBeNull();
    expect(screen.queryByText("Permission denied")).toBeNull();
    // The query has ended on the refusal without a retry in flight.
    await waitFor(() => {
      expect(queryClient.isFetching()).toBe(0);
    });
    expect(refused).toHaveLength(1);
  });
});
