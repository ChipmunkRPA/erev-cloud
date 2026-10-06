// @vitest-environment jsdom
// SF-12 bulk approval (BUILD_SPEC WEB-16; SCREENS §15.5, §15.10, §0.6 SCR-PERM-05; 04 API-R-09 `POST
// /approvals/bulk-approve`, §16.10; REQ-PLT-014, REQ-PLT-017): "Select for bulk approval" switches
// Waiting for me to a multi-selectable grid; the modal takes the comment and the statement that every
// item was reviewed; the command sends each item with the hashes of its own row, after one step-up;
// a refusal is listed by request with its problem; when every item is approved a toast says so.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeAll, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import { NBSP, registerCurrencies } from "../../lib/format";
import type { Approval } from "../../lib/api/queries/approvals";
import {
  installMemoryStorage,
  preloadScreens,
  renderApp,
  signedInMe,
  signedInSession,
} from "../../test/app";
import { narrowColumns } from "../../test/grid-headers";
import { installGridViewport } from "../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import { describedBy, REFUSAL_REFERENCE, REFUSAL_TITLE, refusedWith } from "../../test/refusals";
import { bulkColumns, bulkFailures, impactLine } from "./bulk";

installMswServer();
installMemoryStorage();
installGridViewport();

beforeAll(async () => {
  registerCurrencies([{ code: "USD", minor_unit: 2 }]);
  await preloadScreens(SCREEN_ROUTES, ["SF-12", "SF-12:request"]);
});

afterEach(() => {
  cleanup();
});

const GRACE = signedInMe({ permissions: ["contract.read", "contract.approve", "access.approve"] });
const TOMAS = {
  id: "5c1d8a7e-2b4f-4c6d-9e8a-7f6b5c4d3e2a",
  display_name: "Tomás Rivera",
  kind: "USER",
} as const;
const ROLE_B = "1b2c3d4e-5f6a-4b7c-8d9e-0f1a2b3c4d5e";
const ACTIVATION = "8f0c5a1e-3b2d-4c6e-9a7f-1d2e3f4a5b6c";
const PREVIEW_FILE = "9a8b7c6d-5e4f-4a3b-8c2d-1e0f9a8b7c6d";

function approval(overrides: Partial<Approval> = {}): Approval {
  return {
    id: ROLE_B,
    request_no: "APR-000301",
    subject: {
      type: "ROLE_CHANGE",
      id: "6c5d4e3f-2a1b-4c0d-9e8f-7a6b5c4d3e2f",
      display: "Add the custom role Capture role B",
      href: null,
      content_sha256: "b".repeat(64),
      row_version: null,
    },
    summary: "Add the custom role Capture role B",
    status: "PENDING",
    entity: null,
    entities: [],
    entity_count: 0,
    all_entities: false,
    amount: null,
    flags: [],
    routing: { rule_set_version_id: null, rule_key: null },
    preparer: TOMAS,
    submitted_at: "2026-09-12T14:05:00Z",
    decided_at: null,
    voided_at: null,
    void_reason: null,
    current_step_no: 1,
    steps: [
      {
        step_no: 1,
        name: "Access approval",
        required_permission: "access.approve",
        min_approvers: 1,
        status: "ACTIVE",
        decisions: [],
      },
    ],
    impact_preview: null,
    attachments: [],
    can_decide: true,
    content_withheld: false,
    reason_code: null,
    comment: null,
    ...overrides,
  };
}

/** A request with an amount and a stored impact preview: its item carries both hashes. */
function activation(): Approval {
  return approval({
    id: ACTIVATION,
    request_no: "APR-000229",
    subject: {
      type: "CONTRACT_ACTIVATION",
      id: "7d1e2f3a-4b5c-4d6e-8f7a-9b0c1d2e3f4a",
      display: "Activate BG-AVM-0020",
      href: null,
      content_sha256: "a".repeat(64),
      row_version: 3,
    },
    summary: "Activate BG-AVM-0020",
    entity: { id: "2a3b4c5d-6e7f-4a8b-9c0d-1e2f3a4b5c6d", code: "AVM-US", name: "Avenmoor US" },
    entities: [{ id: "2a3b4c5d-6e7f-4a8b-9c0d-1e2f3a4b5c6d", code: "AVM-US", name: "Avenmoor US" }],
    entity_count: 1,
    amount: { amount: "146000.00", currency: "USD" },
    submitted_at: "2026-09-11T09:30:00Z",
    impact_preview: {
      file_id: PREVIEW_FILE,
      sha256: "d".repeat(64),
      summary: {
        revenue_by_period_before: [],
        revenue_by_period_after: [
          { period_key: "FY2026-P02", amount: { amount: "11200.00", currency: "USD" } },
          { period_key: "FY2026-P03", amount: { amount: "12400.00", currency: "USD" } },
        ],
        balances_before: {},
        balances_after: { contract_liability: { amount: "49200.00", currency: "USD" } },
        journal_lines: [{ line_no: 1 }, { line_no: 2 }, { line_no: 3 }],
        catch_up_total: { amount: "96800.00", currency: "USD" },
        criteria_met: null,
      },
    },
  });
}

interface Sent {
  readonly body: unknown;
  readonly idempotencyKey: string | null;
}

interface World {
  waiting: Approval[];
  readonly searches: string[];
  readonly commands: Sent[];
  stepUps: number;
}

/** `GET /approvals` over a small world, with the count read of the tab; the shell's reads. */
function serve(waiting: Approval[]): World {
  const world: World = { waiting, searches: [], commands: [], stepUps: 0 };
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/approvals"), ({ request }) => {
      const url = new URL(request.url);
      world.searches.push(url.search);
      const counting = url.searchParams.get("count") === "true";
      return HttpResponse.json(
        { items: counting ? world.waiting.slice(0, 1) : world.waiting, next_cursor: null },
        { headers: counting ? { "X-Erev-Total-Count": String(world.waiting.length) } : {} },
      );
    }),
    http.post(apiUrl("/api/v1/session/mfa"), () => {
      world.stepUps += 1;
      // API-S-Session after the challenge, as `POST /session/mfa` answers it.
      return HttpResponse.json({ ...signedInSession(), recovery_codes_remaining: null });
    }),
  );
  return world;
}

function open(entry: string) {
  return renderApp(entry, { me: GRACE, screenRoutes: SCREEN_ROUTES });
}

async function bulkGrid(): Promise<HTMLElement> {
  return within(await screen.findByTestId("SF-12-grid-bulk")).findByRole("grid", {
    name: "Requests waiting for me",
  });
}

describe("SF-12 bulk approval", () => {
  it("SF-12 bulk approval and REQ-PLT-017", async () => {
    const world = serve([activation(), approval()]);
    server.use(
      http.post(apiUrl("/api/v1/approvals/bulk-approve"), async ({ request }) => {
        world.commands.push({
          body: await request.json(),
          idempotencyKey: request.headers.get("Idempotency-Key"),
        });
        if (world.commands.length === 1) {
          // BR-PLT-06: the command is refused before any item is decided.
          return problemResponse("mfa-step-up-required", 403, "Confirm with your authenticator");
        }
        world.waiting = [approval()];
        return HttpResponse.json({
          results: [
            { approval_request_id: ACTIVATION, status: "APPROVED", problem: null },
            {
              approval_request_id: ROLE_B,
              status: null,
              problem: {
                type: "https://erev.dev/problems/stale-approval",
                title: "The item changed after it was submitted",
                status: 409,
                detail: "The maker must resubmit it.",
                instance: "urn:erev:request:0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d",
                errors: [],
              },
            },
          ],
        });
      }),
    );
    const { router } = open("/approvals");
    await screen.findByRole("listbox", { name: "Approval requests" });

    // SCREENS §15.5: the switch replaces the master list by a grid with a checkbox column.
    fireEvent.click(screen.getByRole("button", { name: "Select for bulk approval" }));
    const grid = await bulkGrid();
    expect(router.state.location.search).toBe("?layout=bulk");
    expect(screen.queryByRole("listbox", { name: "Approval requests" })).toBeNull();
    expect(grid.getAttribute("aria-multiselectable")).toBe("true");
    expect(
      within(grid)
        .getAllByRole("columnheader")
        .map((header) => header.textContent.trim())
        .filter((text) => text !== ""),
    ).toEqual(["Request", "Type", "Currency", "Amount", "Preparer", "Submitted"]);
    const row = await within(grid).findByTestId("SF-12-row-apr-000229");
    for (const text of ["APR-000229", "Activate BG-AVM-0020", "Contract activation", "USD"]) {
      expect(within(row).getByText(text)).toBeTruthy();
    }
    expect(within(row).getByText("146,000.00")).toBeTruthy();
    expect(within(row).getByText("Tomás Rivera")).toBeTruthy();
    expect(within(row).getByText("11 Sep 2026")).toBeTruthy();
    // The grid reads the binding of Waiting for me, oldest first.
    expect(world.searches.some((search) => search.includes("assigned_to_me=true"))).toBe(true);

    // Two rows selected: "2 selected" and "Approve 2 items".
    fireEvent.click(within(grid).getByRole("checkbox", { name: "Select Activate BG-AVM-0020" }));
    fireEvent.click(
      within(grid).getByRole("checkbox", { name: "Select Add the custom role Capture role B" }),
    );
    const bar = await screen.findByRole("region", { name: "2 selected" });
    fireEvent.click(within(bar).getByRole("button", { name: "Approve 2 items" }));

    const dialog = await screen.findByRole("dialog", { name: "Approve 2 items" });
    expect(dialog.getAttribute("data-testid")).toBe("SF-12-dialog-bulk-approve");
    const items = within(dialog).getByRole("table", { name: "Selected requests" });
    expect(
      within(items).getByText("Catch-up USD 96,800.00 · Revenue in 2 periods · 3 journal lines"),
    ).toBeTruthy();
    expect(within(items).getByText("No impact on revenue or balances.")).toBeTruthy();
    expect(within(items).getByText("USD 146,000.00")).toBeTruthy();

    // The comment and the statement are required: nothing is sent without them.
    const reviewed = within(dialog).getByRole("checkbox", {
      name: "I reviewed the changes and impact of every selected item.",
    });
    const comment = within(dialog).getByRole("textbox", { name: /^Comment \(required\)/ });
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve 2 items" }));
    expect(await within(dialog).findByText("Enter at least 10 characters.")).toBeTruthy();
    expect(within(dialog).getByText("Confirm that you reviewed every selected item.")).toBeTruthy();
    expect(reviewed.getAttribute("aria-invalid")).toBe("true");
    expect(world.commands).toEqual([]);

    fireEvent.change(comment, { target: { value: "Reviewed with the September close." } });
    fireEvent.click(reviewed);
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve 2 items" }));

    // SCR-PERM-05: one step-up, then the same command with the same key.
    const stepUp = await screen.findByRole("dialog", { name: "Confirm with your authenticator" });
    expect(world.commands).toHaveLength(1);
    fireEvent.change(within(stepUp).getByRole("textbox", { name: /^Authentication code/ }), {
      target: { value: "123456" },
    });
    fireEvent.click(within(stepUp).getByRole("button", { name: "Confirm" }));

    // REQ-PLT-017: each refusal by request, with the problem of its own item.
    const result = await screen.findByRole("dialog", { name: "Approved 1 of 2 items" });
    expect(world.stepUps).toBe(1);
    expect(world.commands).toHaveLength(2);
    expect(world.commands[1]?.idempotencyKey).toBe(world.commands[0]?.idempotencyKey);
    // REQ-PLT-014: every item carries the hashes of its own row.
    expect(world.commands[1]?.body).toEqual({
      comment: "Reviewed with the September close.",
      items: [
        {
          approval_request_id: ACTIVATION,
          subject_content_sha256: "a".repeat(64),
          impact_preview_sha256: "d".repeat(64),
        },
        { approval_request_id: ROLE_B, subject_content_sha256: "b".repeat(64) },
      ],
    });
    const failures = within(result).getByRole("table", { name: "Requests that were not approved" });
    const failed = within(failures).getAllByRole("row")[1] as HTMLElement;
    expect(within(failed).getByText("APR-000301")).toBeTruthy();
    expect(within(failed).getByText("Add the custom role Capture role B")).toBeTruthy();
    expect(within(failed).getByText("The item changed after it was submitted")).toBeTruthy();
    expect(within(failed).getByText("The maker must resubmit it.")).toBeTruthy();
    expect(within(failures).queryByText("Activate BG-AVM-0020")).toBeNull();
    expect(screen.queryByRole("dialog", { name: "Approve 2 items" })).toBeNull();

    // The result closes onto a grid without the selection of the decided rows.
    fireEvent.click(within(result).getByRole("button", { name: "Done" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "Approved 1 of 2 items" })).toBeNull(),
    );
    expect(screen.queryByRole("region", { name: /selected$/ })).toBeNull();
    const after = await bulkGrid();
    await waitFor(() => expect(within(after).queryByTestId("SF-12-row-apr-000229")).toBeNull());
    expect(within(after).getByTestId("SF-12-row-apr-000301")).toBeTruthy();
  });

  it("when every item is approved a toast says so and the selection ends", async () => {
    const world = serve([activation(), approval()]);
    server.use(
      http.post(apiUrl("/api/v1/approvals/bulk-approve"), async ({ request }) => {
        world.commands.push({
          body: await request.json(),
          idempotencyKey: request.headers.get("Idempotency-Key"),
        });
        world.waiting = [];
        return HttpResponse.json({
          results: [
            { approval_request_id: ACTIVATION, status: "APPROVED", problem: null },
            { approval_request_id: ROLE_B, status: "APPROVED", problem: null },
          ],
        });
      }),
    );
    open("/approvals?layout=bulk");
    const grid = await bulkGrid();
    fireEvent.click(await within(grid).findByRole("checkbox", { name: "Select loaded rows" }));
    fireEvent.click(await screen.findByRole("button", { name: "Approve 2 items" }));
    const dialog = await screen.findByRole("dialog", { name: "Approve 2 items" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: /^Comment \(required\)/ }), {
      target: { value: "Both roles reviewed." },
    });
    fireEvent.click(
      within(dialog).getByRole("checkbox", {
        name: "I reviewed the changes and impact of every selected item.",
      }),
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve 2 items" }));

    expect(await screen.findByText("Approved 2 items.")).toBeTruthy();
    expect(world.stepUps).toBe(0);
    expect(world.commands).toHaveLength(1);
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    // The list is empty now: the empty copy of Waiting for me.
    expect(
      await screen.findByRole("heading", { name: "No requests waiting for you" }),
    ).toBeTruthy();
  });

  // docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): a message that names an item of
  // the selection was shown nowhere; the comment's message stands at its field and is not said twice.
  it("a refused bulk approval: the banner lists what the comment field does not show", async () => {
    const noField = "This request was decided since the list was read.";
    const atComment = "Say what was reviewed.";
    serve([activation(), approval()]);
    server.use(
      http.post(apiUrl("/api/v1/approvals/bulk-approve"), () =>
        refusedWith({ "items.1.subject_content_sha256": noField, comment: atComment }),
      ),
    );
    open("/approvals?layout=bulk");
    const grid = await bulkGrid();
    fireEvent.click(await within(grid).findByRole("checkbox", { name: "Select loaded rows" }));
    fireEvent.click(await screen.findByRole("button", { name: "Approve 2 items" }));
    const dialog = await screen.findByRole("dialog", { name: "Approve 2 items" });
    const comment = within(dialog).getByRole("textbox", { name: /^Comment \(required\)/ });
    fireEvent.change(comment, { target: { value: "Both roles reviewed." } });
    fireEvent.click(
      within(dialog).getByRole("checkbox", {
        name: "I reviewed the changes and impact of every selected item.",
      }),
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "Approve 2 items" }));

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + noField + REFUSAL_REFERENCE);
    expect(describedBy(comment)).toContain(atComment);
  });

  it("Exit bulk selection returns to the list, and a request open in the pane closes for the grid", async () => {
    serve([approval()]);
    const { router } = open(`/approvals/requests/${ROLE_B}?view=waiting`);
    server.use(
      http.get(apiUrl(`/api/v1/approvals/${ROLE_B}`), () => HttpResponse.json(approval())),
    );
    await screen.findByRole("listbox", { name: "Approval requests" });
    fireEvent.click(screen.getByRole("button", { name: "Select for bulk approval" }));
    await bulkGrid();
    expect(router.state.location.pathname).toBe("/approvals");
    expect(router.state.location.search).toBe("?layout=bulk");

    fireEvent.click(screen.getByRole("button", { name: "Exit bulk selection" }));
    expect(await screen.findByRole("listbox", { name: "Approval requests" })).toBeTruthy();
    expect(router.state.location.search).toBe("");
    expect(screen.queryByTestId("SF-12-grid-bulk")).toBeNull();
  });

  it("the bulk grid keeps the chips of the view", async () => {
    const world = serve([approval()]);
    const { router } = open("/approvals?f.type=is:ROLE_CHANGE");
    await screen.findByRole("listbox", { name: "Approval requests" });
    fireEvent.click(screen.getByRole("button", { name: "Select for bulk approval" }));
    await bulkGrid();
    // SCR-URL-20: `layout` sits before the chips.
    expect(router.state.location.search).toBe("?layout=bulk&f.type=is:ROLE_CHANGE");
    await waitFor(() =>
      expect(
        world.searches.some(
          (search) =>
            search.includes("subject_type=ROLE_CHANGE") &&
            search.includes("assigned_to_me=true") &&
            search.includes("limit=200"),
        ),
      ).toBe(true),
    );
    expect(
      within(screen.getByTestId("SF-12-filter-bar")).getByRole("button", {
        name: "Type is Role change, edit filter",
      }),
    ).toBeTruthy();
  });

  it("a member without an approval permission has no bulk switch", async () => {
    serve([]);
    renderApp("/approvals", {
      me: signedInMe({ permissions: ["contract.read"] }),
      screenRoutes: SCREEN_ROUTES,
    });
    expect(
      await screen.findByRole("heading", { name: "You have no approval permissions" }),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Select for bulk approval" })).toBeNull();
  });
});

describe("the bulk command as the screen reads it", () => {
  it("every column holds its header, and the grid fits the page at 1440 px", () => {
    const columns = bulkColumns();
    // The "Currency" column was 88 px: its label had 44 of the 58 px it needs (e2e on main 5c2edff7).
    expect(narrowColumns(columns)).toEqual([]);
    // The checkbox column (40 px) and the six columns: 1,144 of the grid's 1,158 px at 1440 px.
    expect(40 + columns.reduce((sum, column) => sum + (column.width ?? 0), 0)).toBe(1144);
    // Request is the widest: two requests of one kind differ at the end of their summaries
    // ("Add the custom role Capture role B", "… role D" read alike when cut at 336 px).
    const [request, ...others] = columns;
    expect(request?.id).toBe("request");
    expect(Math.max(...others.map((column) => column.width ?? 0))).toBeLessThan(
      request?.width ?? 0,
    );
    expect(request?.width).toBeGreaterThanOrEqual(400);
  });

  it("the impact line states what the preview's summary holds, without arithmetic", () => {
    expect(impactLine(approval())).toBe("No impact on revenue or balances.");
    // DS-FMT-05: the code and the figures of an inline amount are joined by a no-break space.
    expect(impactLine(activation()).replaceAll(NBSP, " ")).toBe(
      "Catch-up USD 96,800.00 · Revenue in 2 periods · 3 journal lines",
    );
    const balancesOnly = activation();
    expect(
      impactLine({
        ...balancesOnly,
        impact_preview: {
          file_id: PREVIEW_FILE,
          sha256: "d".repeat(64),
          summary: {
            revenue_by_period_before: [],
            revenue_by_period_after: [],
            balances_before: {},
            balances_after: { contract_liability: { amount: "49200.00", currency: "USD" } },
            journal_lines: [],
            catch_up_total: null,
            criteria_met: null,
          },
        },
      }),
    ).toBe("Figures in the impact preview");
  });

  it("a refusal carries its problem's title, detail and field messages", () => {
    const failures = bulkFailures(
      [activation(), approval()],
      [
        { approval_request_id: ACTIVATION, status: "APPROVED", problem: null },
        {
          approval_request_id: ROLE_B,
          status: null,
          problem: {
            type: "https://erev.dev/problems/invalid-transition",
            title: "The request cannot be approved",
            status: 409,
            instance: "urn:erev:request:0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d",
            errors: [{ field: "impact_preview", message: "The preview could not be read." }],
          },
        },
      ],
    );
    expect(failures).toHaveLength(1);
    expect(failures[0]?.approval.id).toBe(ROLE_B);
    expect(failures[0]?.title).toBe("The request cannot be approved");
    expect(failures[0]?.detail).toBe("The preview could not be read.");
  });

  it("a refusal for a reached effective date carries the approver's sentence, and a detail that repeats a message is said once", () => {
    // PRD §5.5 ERR-75 at the decision: `detail` and `errors[].message` are the author's sentence.
    const authors =
      "This version replaces a published one. Choose an effective date later than today.";
    const failures = bulkFailures(
      [activation(), approval()],
      [
        {
          approval_request_id: ACTIVATION,
          status: null,
          problem: {
            type: "https://erev.dev/problems/validation-failed",
            title: "Check the highlighted fields",
            status: 422,
            detail: authors,
            instance: "urn:erev:request:0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d",
            errors: [{ field: "effective_from", rule_id: "REQ-POL-007", message: authors }],
          },
        },
        {
          approval_request_id: ROLE_B,
          status: null,
          problem: {
            type: "https://erev.dev/problems/invalid-transition",
            title: "The request cannot be approved",
            status: 409,
            detail: "The preview could not be read.",
            instance: "urn:erev:request:0d9c4c1e-2f5b-4a8e-9b7d-3c6a1e2f4b5d",
            errors: [{ field: "impact_preview", message: "The preview could not be read." }],
          },
        },
      ],
    );
    expect(failures.map((failure) => failure.approval.id)).toEqual([ACTIVATION, ROLE_B]);
    // The approver has no effective-date field: the title does not point at one.
    expect(failures[0]?.title).toBe("Effective date reached");
    expect(failures[0]?.detail).toBe(
      `This version replaces a published one and its effective date has been reached, so it can no longer be approved. Reject the request, or ask ${activation().preparer.display_name} to withdraw it: the version can then be given a later date and submitted again.`,
    );
    expect(failures[1]?.detail).toBe("The preview could not be read.");
  });
});
