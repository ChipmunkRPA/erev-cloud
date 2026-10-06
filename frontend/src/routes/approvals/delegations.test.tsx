// @vitest-environment jsdom
// SF-12:delegations (BUILD_SPEC WEB-16; SCREENS §15.7, §0.4 RT-58, §0.6 SCR-PERM-01, SCR-PERM-05; 04
// API-R-09, T-PLT-21; PRD BR-PLT-06, BR-PLT-07): the grid of the delegations a member gave and received
// with the status read from their instants; "New delegation" with the delegate chosen among the other
// active members, the viewer's own approval permissions and a window of at most 90 days sent as whole
// days; "Revoke delegation" with its reason; the step-up of both commands; the empty state; the member
// without the directory and the member without an approval permission.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

import { SCREEN_ROUTES } from "../../app/router";
import { accessOf } from "../../lib/access";
import {
  type Delegation,
  delegationStatus,
  delegationWithinLimit,
} from "../../lib/api/queries/approval-delegations";
import type { UserItem } from "../../lib/api/queries/users";
import {
  installMemoryStorage,
  MEMBERSHIP_ID,
  preloadScreens,
  renderApp,
  signedInMe,
  signedInSession,
} from "../../test/app";
import { narrowColumns } from "../../test/grid-headers";
import { installGridViewport } from "../../test/layout";
import { apiUrl, installMswServer, problemResponse, server } from "../../test/msw";
import { describedBy, REFUSAL_REFERENCE, REFUSAL_TITLE, refusedWith } from "../../test/refusals";
import {
  delegationColumns,
  delegationColumnState,
  GRID_WIDTH_1440,
  ownApprovalPermissions,
  permissionLabel,
  revocable,
  scrolledWidth,
} from "./delegations";

installMswServer();
installMemoryStorage();
installGridViewport();

/** Platform time of the tests: 12 Sep 2026 16:40 UTC. */
const NOW = Date.UTC(2026, 8, 12, 16, 40, 0);

beforeAll(async () => {
  await preloadScreens(SCREEN_ROUTES, ["SF-12", "SF-12:delegations"]);
});

beforeEach(() => {
  vi.useFakeTimers({ toFake: ["Date"] });
  vi.setSystemTime(NOW);
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

const VIEWER = signedInMe({
  permissions: ["contract.read", "contract.approve", "modification.approve", "user.manage"],
});
const MAYA = { id: VIEWER.user.id, kind: "USER", display_name: "Maya Chen" } as const;
const MARCUS = {
  id: "7e3f0c9a-4d6b-4e8f-9a0c-9b8d7e6f5a4c",
  kind: "USER",
  display_name: "Marcus Webb",
} as const;
const ELENA = {
  id: "8f4a1d0b-5e7c-4f9a-8b1d-0c9e8f7a6b5d",
  kind: "USER",
  display_name: "Elena Sokolova",
} as const;
const MARCUS_MEMBERSHIP = "4b5c6d7e-8f9a-4b2c-8d3e-4f5a6b7c8d9e";
const ELENA_MEMBERSHIP = "5c6d7e8f-9a0b-4c3d-9e4f-5a6b7c8d9e0f";
const GIVEN = "a1b2c3d4-e5f6-4a7b-8c9d-0e1f2a3b4c5d";
const RECEIVED = "b2c3d4e5-f6a7-4b8c-9d0e-1f2a3b4c5d6e";
const REVOKED = "c3d4e5f6-a7b8-4c9d-8e1f-2a3b4c5d6e7f";
const AHEAD = "d4e5f6a7-b8c9-4d0e-9f2a-3b4c5d6e7f8a";
const CREATED = "e5f6a7b8-c9d0-4e1f-8a3b-4c5d6e7f8a9b";

function delegation(overrides: Partial<Delegation> = {}): Delegation {
  return {
    id: GIVEN,
    delegator_membership_id: MEMBERSHIP_ID,
    delegator: MAYA,
    delegate_membership_id: MARCUS_MEMBERSHIP,
    delegate: MARCUS,
    permissions: ["contract.approve", "modification.approve"],
    valid_from: "2026-09-10T00:00:00Z",
    valid_to: "2026-09-25T23:59:59Z",
    reason: "Annual leave from 14 to 25 September.",
    revoked_at: null,
    revoked_by: null,
    created_at: "2026-09-09T15:00:00Z",
    created_by: MAYA,
    ...overrides,
  };
}

function member(id: string, userId: string, displayName: string, email: string): UserItem {
  return {
    id,
    user_id: userId,
    display_name: displayName,
    email,
    status: "ACTIVE",
    roles: [],
    mfa_enrolled: true,
    sign_in_withheld: false,
    invited_at: "2026-01-05T09:00:00Z",
    invitation_expires_at: null,
    activated_at: "2026-01-05T10:00:00Z",
    last_login_at: "2026-09-12T08:00:00Z",
    removed_at: null,
    created_at: "2026-01-05T09:00:00Z",
    updated_at: "2026-01-05T10:00:00Z",
    row_version: 2,
  };
}

interface Sent {
  readonly path: string;
  readonly body: unknown;
  readonly idempotencyKey: string | null;
}

interface World {
  delegations: Delegation[];
  readonly searches: string[];
  readonly userSearches: string[];
  readonly commands: Sent[];
  stepUps: number;
}

function serve(delegations: Delegation[]): World {
  const world: World = { delegations, searches: [], userSearches: [], commands: [], stepUps: 0 };
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/approvals"), () =>
      HttpResponse.json(
        { items: [], next_cursor: null },
        { headers: { "X-Erev-Total-Count": "0" } },
      ),
    ),
    http.get(apiUrl("/api/v1/approval-delegations"), ({ request }) => {
      const url = new URL(request.url);
      world.searches.push(url.search);
      return HttpResponse.json(
        { items: world.delegations, next_cursor: null },
        { headers: { "X-Erev-Total-Count": String(world.delegations.length) } },
      );
    }),
    http.get(apiUrl("/api/v1/users"), ({ request }) => {
      world.userSearches.push(new URL(request.url).search);
      return HttpResponse.json({
        items: [
          member(ELENA_MEMBERSHIP, ELENA.id, "Elena Sokolova", "elena@example.test"),
          member(MARCUS_MEMBERSHIP, MARCUS.id, "Marcus Webb", "marcus@example.test"),
          member(MEMBERSHIP_ID, MAYA.id, "Maya Chen", "maya@example.test"),
        ],
        next_cursor: null,
      });
    }),
    http.post(apiUrl("/api/v1/session/mfa"), () => {
      world.stepUps += 1;
      return HttpResponse.json({ ...signedInSession(), recovery_codes_remaining: null });
    }),
  );
  return world;
}

function open(me = VIEWER) {
  return renderApp("/approvals/delegations", { me, screenRoutes: SCREEN_ROUTES });
}

async function grid(): Promise<HTMLElement> {
  return within(await screen.findByTestId("SF-12-grid-delegations")).findByRole("grid", {
    name: "Delegations",
  });
}

/** The data row that holds `text`. */
function rowWith(root: HTMLElement, text: string): HTMLElement {
  const found = within(root)
    .getAllByRole("row")
    .find((row) => within(row).queryByText(text) !== null);
  if (found === undefined) {
    throw new Error(`no row holds "${text}"`);
  }
  return found;
}

async function record(world: World, request: Request): Promise<void> {
  world.commands.push({
    path: new URL(request.url).pathname,
    body: await request.json(),
    idempotencyKey: request.headers.get("Idempotency-Key"),
  });
}

describe("SF-12:delegations", () => {
  it("SF-12:delegations", async () => {
    const world = serve([
      delegation(),
      delegation({
        id: RECEIVED,
        delegator_membership_id: ELENA_MEMBERSHIP,
        delegator: ELENA,
        delegate_membership_id: MEMBERSHIP_ID,
        delegate: MAYA,
        permissions: ["contract.approve"],
        valid_from: "2026-08-01T00:00:00Z",
        valid_to: "2026-08-15T23:59:59Z",
        reason: "Covering the August close.",
        created_at: "2026-07-30T10:00:00Z",
        created_by: ELENA,
      }),
      delegation({
        id: REVOKED,
        reason: "Conference week in June.",
        valid_from: "2026-06-01T00:00:00Z",
        valid_to: "2026-06-30T23:59:59Z",
        revoked_at: "2026-06-05T09:00:00Z",
        revoked_by: MAYA,
      }),
      delegation({
        id: AHEAD,
        reason: "Planned leave in October.",
        valid_from: "2026-10-05T00:00:00Z",
        valid_to: "2026-10-16T23:59:59Z",
      }),
    ]);
    server.use(
      http.post(apiUrl("/api/v1/approval-delegations"), async ({ request }) => {
        await record(world, request);
        if (world.commands.length === 1) {
          return problemResponse("mfa-step-up-required", 403, "Confirm with your authenticator");
        }
        const created = delegation({
          id: CREATED,
          permissions: ["contract.approve"],
          valid_from: "2026-09-12T00:00:00Z",
          valid_to: "2026-09-30T23:59:59Z",
          reason: "Out of office until the end of September.",
          created_at: "2026-09-12T16:40:00Z",
        });
        world.delegations = [created, ...world.delegations];
        return HttpResponse.json(created, { status: 201 });
      }),
      http.post(apiUrl(`/api/v1/approval-delegations/${GIVEN}/revoke`), async ({ request }) => {
        await record(world, request);
        const revoked = delegation({ revoked_at: "2026-09-12T16:41:00Z", revoked_by: MAYA });
        world.delegations = world.delegations.map((item) => (item.id === GIVEN ? revoked : item));
        return HttpResponse.json(revoked);
      }),
    );
    open();

    // SCREENS §15.3: the Approvals header with the Delegations tab on its page.
    expect(await screen.findByRole("heading", { level: 1, name: "Approvals" })).toBeTruthy();
    expect(
      (await screen.findByRole("link", { name: "Delegations" })).getAttribute("aria-current"),
    ).toBe("page");

    // The grid binds GET /approval-delegations: what the member gave and received, newest first.
    const table = await grid();
    await waitFor(() => expect(world.searches.length).toBeGreaterThan(0));
    expect(new URLSearchParams(world.searches[0]).get("sort")).toBeNull();
    expect(
      within(table)
        .getAllByRole("columnheader")
        .map((header) => header.textContent.trim()),
    ).toEqual([
      "Delegate",
      "Delegator",
      "Permissions",
      "Valid from",
      "Valid to",
      "Reason",
      "Status",
      "Created at",
      "Actions",
    ]);
    const given = rowWith(table, "Annual leave from 14 to 25 September.");
    for (const text of [
      "Marcus Webb",
      "Maya Chen",
      "Approve contract activation, Approve contract modifications",
      "10 Sep 2026",
      "25 Sep 2026",
      "Active",
      "09 Sep 2026 15:00 UTC",
    ]) {
      expect(within(given).getByText(text)).toBeTruthy();
    }
    // A delegation received has ended: no command for the delegate, the delegator alone revokes.
    const received = rowWith(table, "Covering the August close.");
    expect(within(received).getByText("Expired")).toBeTruthy();
    expect(within(received).queryByRole("button", { name: "Revoke delegation" })).toBeNull();
    const revokedRow = rowWith(table, "Conference week in June.");
    expect(within(revokedRow).getByText("Revoked")).toBeTruthy();
    expect(within(revokedRow).queryByRole("button", { name: "Revoke delegation" })).toBeNull();
    const ahead = rowWith(table, "Planned leave in October.");
    expect(within(ahead).getByText("Not started")).toBeTruthy();
    expect(within(ahead).getByRole("button", { name: "Revoke delegation" })).toBeTruthy();

    // New delegation: the viewer is no choice of Delegate.
    fireEvent.click(screen.getByRole("button", { name: "New delegation" }));
    const drawer = await screen.findByRole("dialog", { name: "New delegation" });
    await waitFor(() => expect(world.userSearches.length).toBeGreaterThan(0));
    expect(new URLSearchParams(world.userSearches[0]).getAll("status")).toEqual(["ACTIVE"]);
    const delegate = within(drawer).getByRole("combobox", { name: /^Delegate/ });
    fireEvent.keyDown(delegate, { key: "ArrowDown" });
    await waitFor(() =>
      expect(
        within(drawer)
          .getAllByRole("option")
          .map((option) => option.textContent),
      ).toEqual(["Elena Sokolova · elena@example.test", "Marcus Webb · marcus@example.test"]),
    );
    fireEvent.mouseDown(within(drawer).getByRole("option", { name: /^Marcus Webb/ }));

    // Only the approval permissions the viewer holds.
    const permissions = within(drawer).getByRole("group", { name: "Permissions" });
    expect(
      within(permissions)
        .getAllByRole("checkbox")
        .map((box) => box.closest("label")?.textContent),
    ).toEqual(["Approve contract activation", "Approve contract modifications"]);

    // The window opens today and lasts at most 90 days, its last day included.
    const from = within(drawer).getByLabelText(/^Valid from/) as HTMLInputElement;
    const to = within(drawer).getByLabelText(/^Valid to/);
    expect(from.value).toBe("12 Sep 2026");
    fireEvent.change(to, { target: { value: "2026-12-12" } });
    fireEvent.blur(to);
    expect(await within(drawer).findByText("A delegation lasts at most 90 days.")).toBeTruthy();
    fireEvent.change(to, { target: { value: "2026-12-11" } });
    fireEvent.blur(to);
    expect(within(drawer).getByText("A delegation lasts at most 90 days.")).toBeTruthy();
    fireEvent.change(to, { target: { value: "2026-12-10" } });
    fireEvent.blur(to);
    await waitFor(() =>
      expect(within(drawer).queryByText("A delegation lasts at most 90 days.")).toBeNull(),
    );

    // An incomplete form names what is missing and sends nothing.
    fireEvent.click(within(drawer).getByRole("button", { name: "Create delegation" }));
    expect(await within(drawer).findByText("Select at least one permission.")).toBeTruthy();
    expect(within(drawer).getByText("Enter at least 10 characters.")).toBeTruthy();
    expect(world.commands).toEqual([]);

    fireEvent.click(
      within(permissions).getByRole("checkbox", { name: "Approve contract activation" }),
    );
    fireEvent.change(to, { target: { value: "2026-09-30" } });
    fireEvent.blur(to);
    fireEvent.change(within(drawer).getByRole("textbox", { name: /^Reason/ }), {
      target: { value: "Out of office until the end of September." },
    });
    fireEvent.click(within(drawer).getByRole("button", { name: "Create delegation" }));

    // SCR-PERM-05: the step-up, then the same command with the same key.
    const stepUp = await screen.findByRole("dialog", { name: "Confirm with your authenticator" });
    fireEvent.change(within(stepUp).getByRole("textbox", { name: /^Authentication code/ }), {
      target: { value: "123456" },
    });
    fireEvent.click(within(stepUp).getByRole("button", { name: "Confirm" }));
    expect(await screen.findByText("Delegated to Marcus Webb until 30 Sep 2026.")).toBeTruthy();
    expect(world.stepUps).toBe(1);
    expect(world.commands).toHaveLength(2);
    expect(world.commands[1]?.idempotencyKey).toBe(world.commands[0]?.idempotencyKey);
    // DS-I18N-08: whole days in platform time, the last day included.
    expect(world.commands[1]?.body).toEqual({
      delegate_membership_id: MARCUS_MEMBERSHIP,
      permissions: ["contract.approve"],
      valid_from: "2026-09-12T00:00:00Z",
      valid_to: "2026-09-30T23:59:59Z",
      reason: "Out of office until the end of September.",
    });
    await waitFor(() =>
      expect(screen.queryByRole("dialog", { name: "New delegation" })).toBeNull(),
    );
    expect(
      await within(await grid()).findByText("Out of office until the end of September."),
    ).toBeTruthy();

    // Revoke delegation requires a reason.
    fireEvent.click(
      within(rowWith(await grid(), "Annual leave from 14 to 25 September.")).getByRole("button", {
        name: "Revoke delegation",
      }),
    );
    const confirm = await screen.findByRole("alertdialog", {
      name: "Revoke the delegation to Marcus Webb?",
    });
    expect(
      within(confirm).getByText(
        "Marcus Webb can no longer approve on your behalf. Decisions already recorded stay as they are.",
      ),
    ).toBeTruthy();
    fireEvent.click(within(confirm).getByRole("button", { name: "Revoke delegation" }));
    expect(await within(confirm).findByText("Enter at least 10 characters.")).toBeTruthy();
    expect(world.commands).toHaveLength(2);
    fireEvent.change(within(confirm).getByRole("textbox", { name: /^Reason/ }), {
      target: { value: "Back at work earlier than planned." },
    });
    fireEvent.click(within(confirm).getByRole("button", { name: "Revoke delegation" }));
    expect(await screen.findByText("Revoked the delegation to Marcus Webb.")).toBeTruthy();
    expect(world.commands[2]).toMatchObject({
      path: `/api/v1/approval-delegations/${GIVEN}/revoke`,
      body: { reason: "Back at work earlier than planned." },
    });
    await waitFor(() =>
      expect(
        within(
          rowWith(
            screen.getByTestId("SF-12-grid-delegations"),
            "Annual leave from 14 to 25 September.",
          ),
        ).queryByText("Revoked"),
      ).not.toBeNull(),
    );
  });

  it("the empty state names what belongs here and offers the first delegation", async () => {
    serve([]);
    open();
    const empty = await screen.findByTestId("SF-12-empty-delegations");
    // SCREENS §15.7: "No delegations. Delegate approval permissions for up to 90 days when you are away."
    expect(within(empty).getByRole("heading", { name: "No delegations" })).toBeTruthy();
    expect(
      within(empty).getByText("Delegate approval permissions for up to 90 days when you are away."),
    ).toBeTruthy();
    fireEvent.click(within(empty).getByRole("button", { name: "New delegation" }));
    expect(await screen.findByRole("dialog", { name: "New delegation" })).toBeTruthy();
  });

  it("the API's refusal of a delegate or a permission is shown on its field", async () => {
    const world = serve([]);
    server.use(
      http.post(apiUrl("/api/v1/approval-delegations"), async ({ request }) => {
        await record(world, request);
        return problemResponse("validation-failed", 422, "Validation failed", {
          errors: [
            {
              field: "delegate_membership_id",
              rule_id: "T-PLT-21",
              message: "Choose an active member of this workspace.",
            },
            {
              field: "permissions[0]",
              rule_id: "T-PLT-21",
              message: "You can delegate only approval permissions you hold.",
            },
          ],
        });
      }),
    );
    open();
    fireEvent.click(
      (await screen.findAllByRole("button", { name: "New delegation" }))[0] as HTMLElement,
    );
    const drawer = await screen.findByRole("dialog", { name: "New delegation" });
    const delegate = within(drawer).getByRole("combobox", { name: /^Delegate/ });
    fireEvent.keyDown(delegate, { key: "ArrowDown" });
    fireEvent.mouseDown(await within(drawer).findByRole("option", { name: /^Elena Sokolova/ }));
    fireEvent.click(
      within(drawer).getByRole("checkbox", { name: "Approve contract modifications" }),
    );
    const to = within(drawer).getByLabelText(/^Valid to/);
    fireEvent.change(to, { target: { value: "2026-09-20" } });
    fireEvent.blur(to);
    fireEvent.change(within(drawer).getByRole("textbox", { name: /^Reason/ }), {
      target: { value: "A week away from the desk." },
    });
    fireEvent.click(within(drawer).getByRole("button", { name: "Create delegation" }));

    expect(
      await within(drawer).findByText("Choose an active member of this workspace."),
    ).toBeTruthy();
    expect(
      within(drawer).getByText("You can delegate only approval permissions you hold."),
    ).toBeTruthy();
    expect(delegate.getAttribute("aria-invalid")).toBe("true");
    expect(world.commands[0]?.body).toMatchObject({
      delegate_membership_id: ELENA_MEMBERSHIP,
      permissions: ["modification.approve"],
    });
  });

  // docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): a message that names a member the
  // form has no field for was shown nowhere; the reason's message stands at its field, not in the banner.
  it("New delegation under a refused command: the banner lists what no field shows", async () => {
    const noField = "A delegation of yours to this member already covers these days.";
    const atReason = "Say who covers for you.";
    serve([]);
    server.use(
      http.post(apiUrl("/api/v1/approval-delegations"), () =>
        refusedWith({ delegator_membership_id: noField, reason: atReason }),
      ),
    );
    open();
    fireEvent.click(
      (await screen.findAllByRole("button", { name: "New delegation" }))[0] as HTMLElement,
    );
    const drawer = await screen.findByRole("dialog", { name: "New delegation" });
    const delegate = within(drawer).getByRole("combobox", { name: /^Delegate/ });
    fireEvent.keyDown(delegate, { key: "ArrowDown" });
    fireEvent.mouseDown(await within(drawer).findByRole("option", { name: /^Elena Sokolova/ }));
    fireEvent.click(
      within(drawer).getByRole("checkbox", { name: "Approve contract modifications" }),
    );
    const to = within(drawer).getByLabelText(/^Valid to/);
    fireEvent.change(to, { target: { value: "2026-09-20" } });
    fireEvent.blur(to);
    const reason = within(drawer).getByRole("textbox", { name: /^Reason/ });
    fireEvent.change(reason, { target: { value: "A week away from the desk." } });
    fireEvent.click(within(drawer).getByRole("button", { name: "Create delegation" }));

    const banner = await within(drawer).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + noField + REFUSAL_REFERENCE);
    expect(describedBy(reason)).toContain(atReason);
  });

  it("Revoke delegation under a refused command: the banner lists what the reason does not show", async () => {
    const noField = "This delegation ended before it was revoked.";
    const atReason = "Say why the delegation ends early.";
    const world = serve([delegation()]);
    server.use(
      http.post(
        apiUrl(`/api/v1/approval-delegations/${world.delegations[0]?.id ?? ""}/revoke`),
        () => refusedWith({ valid_to: noField, reason: atReason }),
      ),
    );
    open();
    fireEvent.click(
      within(rowWith(await grid(), "Annual leave from 14 to 25 September.")).getByRole("button", {
        name: "Revoke delegation",
      }),
    );
    const confirm = await screen.findByRole("alertdialog", {
      name: "Revoke the delegation to Marcus Webb?",
    });
    const reason = within(confirm).getByRole("textbox", { name: /^Reason/ });
    fireEvent.change(reason, { target: { value: "Back at work earlier than planned." } });
    fireEvent.click(within(confirm).getByRole("button", { name: "Revoke delegation" }));

    const banner = await within(confirm).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + noField + REFUSAL_REFERENCE);
    expect(describedBy(reason)).toContain(atReason);
  });

  it("without the member directory New delegation states why it is unavailable", async () => {
    const world = serve([delegation()]);
    open(signedInMe({ permissions: ["contract.read", "contract.approve"] }));
    await grid();
    const add = screen.getByRole("button", { name: "New delegation" });
    expect(add.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(add);
    expect(screen.queryByRole("dialog", { name: "New delegation" })).toBeNull();
    fireEvent.focus(add);
    expect(
      await screen.findByText(
        "Choosing a delegate needs the member directory, which your roles do not include.",
      ),
    ).toBeTruthy();
    // The delegations given can still be revoked.
    expect(
      within(rowWith(await grid(), "Annual leave from 14 to 25 September.")).getByRole("button", {
        name: "Revoke delegation",
      }),
    ).toBeTruthy();
    expect(world.userSearches).toEqual([]);
  });

  it("without an approval permission the screen is access-limited and has no tab", async () => {
    const world = serve([delegation()]);
    open(signedInMe({ permissions: ["contract.read"] }));
    expect(
      await screen.findByRole("heading", { name: "You do not have access to delegations" }),
    ).toBeTruthy();
    expect(
      screen.getByText(
        "Ask a workspace administrator for a role that includes an approval permission.",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Delegations" })).toBeNull();
    expect(screen.queryByTestId("SF-12-grid-delegations")).toBeNull();
    expect(world.searches).toEqual([]);
  });
});

describe("T-PLT-21 as the screen reads it", () => {
  it("the status follows revoked_at and the two instants", () => {
    expect(delegationStatus(delegation(), NOW)).toBe("ACTIVE");
    expect(delegationStatus(delegation({ revoked_at: "2026-09-11T08:00:00Z" }), NOW)).toBe(
      "REVOKED",
    );
    expect(delegationStatus(delegation({ valid_to: "2026-09-12T16:40:00Z" }), NOW)).toBe("EXPIRED");
    expect(delegationStatus(delegation({ valid_from: "2026-09-12T16:40:01Z" }), NOW)).toBe(
      "NOT_STARTED",
    );
  });

  it("only the delegator revokes, and only a delegation still to end", () => {
    expect(revocable(delegation(), MEMBERSHIP_ID, NOW)).toBe(true);
    expect(revocable(delegation(), MARCUS_MEMBERSHIP, NOW)).toBe(false);
    expect(revocable(delegation({ revoked_at: "2026-09-11T08:00:00Z" }), MEMBERSHIP_ID, NOW)).toBe(
      false,
    );
    expect(revocable(delegation({ valid_to: "2026-09-01T23:59:59Z" }), MEMBERSHIP_ID, NOW)).toBe(
      false,
    );
  });

  it("at 1440 px the columns from Delegate to Status fit beside the pinned row action", () => {
    const columns = delegationColumns({
      membershipId: null,
      nowMs: NOW,
      onRevoke: () => undefined,
    });
    const state = delegationColumnState(columns);
    // SCREENS §15.7 order, the Delegator after the Delegate; "Revoke delegation" stays in view.
    expect(state.order).toEqual([
      "delegate",
      "delegator",
      "permissions",
      "valid_from",
      "valid_to",
      "reason",
      "status",
      "created_at",
      "actions",
    ]);
    expect(state.pinned).toEqual({ start: [], end: ["actions"] });
    expect(state.hidden).toEqual([]);
    // Every column holds its header, the three sortable ones with their sort mark.
    expect(narrowColumns(columns)).toEqual([]);
    const action = columns.find((column) => column.id === "actions")?.width ?? 0;
    // Delegate to Status fill the room beside the pinned action to within its last pixels, so no
    // sliver of "Created at" shows at the pinned edge (read from the capture: a cut "C").
    const room = GRID_WIDTH_1440 - action;
    expect(scrolledWidth(columns, "status")).toBeGreaterThanOrEqual(room);
    expect(scrolledWidth(columns, "status")).toBeLessThanOrEqual(room + 8);
    // "Created at" is the one column a 1440 px page scrolls to.
    expect(scrolledWidth(columns, "created_at") + action).toBeGreaterThan(GRID_WIDTH_1440);
  });

  it("90 days count the last day", () => {
    expect(delegationWithinLimit("2026-09-12", "2026-12-10")).toBe(true);
    expect(delegationWithinLimit("2026-09-12", "2026-12-11")).toBe(false);
    expect(delegationWithinLimit("2026-09-12", "2026-09-12")).toBe(true);
  });

  it("permissions are the viewer's approval permissions, labelled from the catalogue", () => {
    expect(
      ownApprovalPermissions(
        accessOf(
          signedInMe({
            permissions: ["contract.read", "access.approve", "contract.approve", "user.manage"],
          }),
        ),
      ),
    ).toEqual(["contract.approve", "access.approve"]);
    expect(permissionLabel("period.reopen_approve")).toBe(
      "Approve the reopening of a closed period",
    );
    expect(permissionLabel("billing.approve")).toBe("billing.approve");
  });
});
