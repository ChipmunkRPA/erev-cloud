// @vitest-environment jsdom
// SF-15:sandbox (BUILD_SPEC SNP-5; SCREENS_B §9.7 data bindings, columns, states, interactions and test
// hooks; SB-R-05, SB-R-06; 04 API-R-04 `GET, POST /tenant/snapshots`, `POST /tenant/sandboxes`, `POST
// /tenant/reset`, API-R-03 `GET /me`, API-R-01 `POST /session/tenant`; PRD J-25, ACT-50, ACT-51): a
// production workspace lists its sandboxes and stored snapshots, copies and restores through a job
// and never renders a reset; a sandbox says what it was copied from and resets behind a confirmation
// with a reason.
import { cleanup, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";

import { SCREEN_ROUTES } from "../../../app/router";
import type { Me } from "../../../lib/api/queries/me";
import { instantMs } from "../../../lib/format";
import { accessDescription } from "../../../test/access";
import {
  installMemoryStorage,
  MEMBERSHIP_ID,
  renderApp,
  signedInMe,
  signedInSession,
} from "../../../test/app";
import { apiUrl, installMswServer, server } from "../../../test/msw";
import { describedBy, REFUSAL_REFERENCE, REFUSAL_TITLE, refusedWith } from "../../../test/refusals";
import { digestPrefix, idPrefix, sandboxesOf, type Snapshot, specificTime } from "../sandbox";

installMswServer();
installMemoryStorage();

afterEach(() => {
  cleanup();
});

const PRODUCTION_ID = "0b6f3e2d-1c4a-4b8e-9d7f-6a5c4b3e2d1f";
const SANDBOX_ID = "1c1c1c1c-1c1c-4c1c-8c1c-1c1c1c1c1c1c";
const ARCHIVED_ID = "2d2d2d2d-2d2d-4d2d-8d2d-2d2d2d2d2d2d";
const COPY_ID = "5b1e0a0a-0000-4000-8000-0000000009ac";
const BACKUP_ID = "6c2f0b0b-0000-4000-8000-000000001bcd";
const RUNNING_ID = "7d300c0c-0000-4000-8000-000000002cde";
const JOB_ID = "9f9f9f9f-9f9f-4f9f-8f9f-9f9f9f9f9f9f";
const NEW_SANDBOX_ID = "3e3e3e3e-3e3e-4e3e-8e3e-3e3e3e3e3e3e";
const MANIFEST = "a0c4e9d1" + "0".repeat(52) + "7e22";

type Membership = Me["memberships"][number];

function membership(
  id: string,
  tenant: Partial<Membership["tenant"]> & Pick<Membership["tenant"], "id" | "display_name">,
): Membership {
  return {
    membership_id: id,
    tenant: {
      code: tenant.display_name.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
      kind: "sandbox",
      is_demo: false,
      status: "ACTIVE",
      source_tenant_id: PRODUCTION_ID,
      source_known_at: "2026-09-12T18:10:00Z",
      ...tenant,
    },
    status: "ACTIVE",
    last_opened_at: null,
  };
}

const PRODUCTION: Membership = {
  membership_id: MEMBERSHIP_ID,
  tenant: {
    id: PRODUCTION_ID,
    code: "avenmoor",
    display_name: "Avenmoor Holdings (Demo)",
    kind: "production",
    is_demo: true,
    status: "ACTIVE",
    source_tenant_id: null,
    source_known_at: null,
  },
  status: "ACTIVE",
  last_opened_at: "2026-09-13T08:00:00Z",
};
const COPY = membership("4a4a4a4a-4a4a-4a4a-8a4a-4a4a4a4a4a4a", {
  id: SANDBOX_ID,
  display_name: "Avenmoor pre-close snapshot (Sandbox)",
});
const ARCHIVED = membership("5b5b5b5b-5b5b-4b5b-8b5b-5b5b5b5b5b5b", {
  id: ARCHIVED_ID,
  display_name: "August rehearsal",
  status: "ARCHIVED",
  source_known_at: "2026-08-31T23:00:00Z",
});

/** Marcus: Controller, so `tenant.snapshot` and `sandbox.reset` (PRD ACT-50, ACT-51). */
function marcus(overrides: Partial<Me> = {}): Me {
  return signedInMe({
    memberships: [PRODUCTION, COPY, ARCHIVED],
    permissions: ["contract.read", "tenant.snapshot", "sandbox.reset"],
    ...overrides,
  });
}

/** API-S-Actor of a member of the workspace (04 §16.0). */
function actor(displayName: string): Snapshot["created_by"] {
  return { id: "5c1d8a7e-2b4f-4c6d-9e8a-7f6b5c4d3e2a", kind: "USER", display_name: displayName };
}

function snapshot(overrides: Partial<Snapshot> & Pick<Snapshot, "id">): Snapshot {
  return {
    known_at: "2026-09-12T18:10:00Z",
    purpose: "SANDBOX_COPY",
    status: "SUCCEEDED",
    target_tenant_id: null,
    manifest_file_id: "8e8e8e8e-8e8e-4e8e-8e8e-8e8e8e8e8e8e",
    manifest_sha256: MANIFEST,
    row_counts: null,
    job_id: null,
    started_at: "2026-09-12T18:10:05Z",
    finished_at: "2026-09-12T18:11:40Z",
    created_at: "2026-09-12T18:10:01Z",
    created_by: actor("Marcus Webb"),
    ...overrides,
  };
}

const SNAPSHOTS: readonly Snapshot[] = [
  snapshot({ id: COPY_ID, target_tenant_id: SANDBOX_ID }),
  snapshot({ id: BACKUP_ID, purpose: "STORED_BACKUP", created_by: actor("Jordan Blake") }),
  snapshot({
    id: RUNNING_ID,
    status: "RUNNING",
    manifest_file_id: null,
    manifest_sha256: null,
    finished_at: null,
  }),
];

function job(state: string, result: Record<string, unknown> | null = null) {
  return {
    id: JOB_ID,
    kind: "TENANT_SNAPSHOT",
    state,
    progress: { done: 0, total: null },
    result,
    problem: null,
    created_by: { id: null, kind: "USER", display_name: "Marcus Webb" },
    created_at: "2026-09-13T08:00:00Z",
    started_at: "2026-09-13T08:00:01Z",
    finished_at: state === "RUNNING" ? null : "2026-09-13T08:01:00Z",
    mode: "restore",
  };
}

/** The shell's reads and the stored snapshots of the workspace. */
function serve(snapshots: readonly Snapshot[] = SNAPSHOTS) {
  server.use(
    http.get(apiUrl("/api/v1/me/notifications"), () =>
      HttpResponse.json({ items: [], next_cursor: null }),
    ),
    http.get(apiUrl("/api/v1/entities"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/books"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/periods"), () => HttpResponse.json({ items: [], next_cursor: null })),
    http.get(apiUrl("/api/v1/tenant/snapshots"), () =>
      HttpResponse.json({ items: snapshots, next_cursor: null }),
    ),
  );
}

const SANDBOX_SESSION = signedInSession({
  active_tenant: {
    id: SANDBOX_ID,
    code: "avenmoor-pre-close-snapshot",
    display_name: "Avenmoor pre-close snapshot (Sandbox)",
    kind: "sandbox",
  },
});
const PRODUCTION_SESSION = signedInSession({
  active_tenant: {
    id: PRODUCTION_ID,
    code: "avenmoor",
    display_name: "Avenmoor Holdings (Demo)",
    kind: "production",
  },
});

function renderSandbox(me: Me = marcus(), session = PRODUCTION_SESSION) {
  return renderApp("/settings/sandbox", { me, session, screenRoutes: SCREEN_ROUTES });
}

/** PRD ERR-77, the form without a confirmed policy. */
const ERR_77 =
  "No snapshot retention policy is confirmed yet. A Tenant Admin sets the retention families and a second person approves them; sandbox copies are possible from the time the approved policy takes effect.";

describe("SF-15:sandbox", () => {
  it("no reset in production", async () => {
    const restored: unknown[] = [];
    serve();
    server.use(
      http.post(apiUrl("/api/v1/tenant/sandboxes"), async ({ request }) => {
        restored.push(await request.json());
        return HttpResponse.json(
          { ...job("RUNNING"), sandbox_tenant_id: NEW_SANDBOX_ID },
          {
            status: 202,
            headers: {
              Location: `/api/v1/jobs/${JOB_ID}`,
              "X-Erev-Sandbox-Tenant-Id": NEW_SANDBOX_ID,
            },
          },
        );
      }),
      http.get(apiUrl(`/api/v1/jobs/${JOB_ID}`), () => HttpResponse.json(job("RUNNING"))),
    );
    renderSandbox();

    expect(await screen.findByRole("heading", { level: 1, name: "Sandbox copies" })).toBeTruthy();
    const sandboxes = await screen.findByRole("table", { name: "Sandboxes" });
    expect(sandboxes.getAttribute("data-testid")).toBe("SF-15-grid-sandboxes");
    expect(screen.getByRole("heading", { level: 2, name: "Sandboxes (2)" })).toBeTruthy();
    const copy = within(sandboxes).getByRole("row", {
      name: /Avenmoor pre-close snapshot \(Sandbox\)/,
    });
    expect(within(copy).getByText("12 Sep 2026 18:10 UTC")).toBeTruthy();
    expect(within(copy).getByText("Active")).toBeTruthy();
    // The row comes from the member's own workspaces; the name of who made the copy comes with the
    // stored snapshots, a later read (VITEST-LIVENESS-2): the case waits for it.
    expect(await within(copy).findByText("Marcus Webb")).toBeTruthy();
    expect(
      within(copy).getByRole("button", { name: "Open Avenmoor pre-close snapshot (Sandbox)" }),
    ).toBeTruthy();
    const archived = within(sandboxes).getByRole("row", { name: /August rehearsal/ });
    expect(within(archived).getByText("Archived")).toBeTruthy();
    expect(within(archived).queryByRole("button")).toBeNull();

    // J-25.4: production renders no reset control at all.
    expect(screen.queryByRole("button", { name: "Reset sandbox" })).toBeNull();

    const stored = await screen.findByRole("table", { name: "Stored snapshots" });
    expect(stored.getAttribute("data-testid")).toBe("SF-15-grid-snapshots");
    expect(screen.getByRole("heading", { level: 2, name: "Stored snapshots (3)" })).toBeTruthy();
    const headers = within(stored)
      .getAllByRole("columnheader")
      .map((header) => header.textContent?.trim() ?? "");
    expect(headers.slice(0, 7)).toEqual([
      "Snapshot",
      "Purpose",
      "Known at",
      "Status",
      "Target sandbox",
      "Manifest SHA-256",
      "Created by",
    ]);
    const copied = within(stored).getByTestId(`SF-15-row-snapshot-${COPY_ID}`);
    expect(within(copied).getByText(idPrefix(COPY_ID))).toBeTruthy();
    expect(within(copied).getByText("Sandbox copy")).toBeTruthy();
    expect(within(copied).getByText("Succeeded")).toBeTruthy();
    expect(within(copied).getByText("Avenmoor pre-close snapshot (Sandbox)")).toBeTruthy();
    expect(within(copied).getByText("a0c4e9d1…7e22")).toBeTruthy();
    const backup = within(stored).getByTestId(`SF-15-row-snapshot-${BACKUP_ID}`);
    expect(within(backup).getByText("Stored backup")).toBeTruthy();
    expect(within(backup).getByText("Jordan Blake")).toBeTruthy();
    // A snapshot that has not succeeded cannot be restored.
    const running = within(stored).getByTestId(`SF-15-row-snapshot-${RUNNING_ID}`);
    expect(within(running).getByText("Running")).toBeTruthy();
    expect(within(running).queryByRole("button")).toBeNull();

    // Stored snapshot rows offer "Restore into a new sandbox" (SCR-LTH-11). The row's control says
    // which snapshot, and its name begins with the words it shows, as "Open" does.
    const restoreBackup = within(backup).getByRole("button", {
      name: `Restore into a new sandbox from snapshot ${idPrefix(BACKUP_ID)}`,
    });
    expect(restoreBackup.textContent).toBe("Restore into a new sandbox");
    fireEvent.click(restoreBackup);
    const dialog = await screen.findByRole("dialog", { name: "Restore into a new sandbox" });
    expect(
      within(dialog).getByText(
        "A new sandbox is created from this snapshot. Production is not changed.",
      ),
    ).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "Restore into a new sandbox" }));
    expect(await within(dialog).findByText("Enter a name.")).toBeTruthy();
    expect(restored).toEqual([]);
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Name" }), {
      target: { value: "  September restore  " },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Restore into a new sandbox" }));
    await waitFor(() => {
      expect(restored).toEqual([{ tenant_snapshot_id: BACKUP_ID, name: "September restore" }]);
    });
    // SB-R-06: the copy's progress shows in place, and the dialog is gone.
    const progress = await screen.findByRole("progressbar", {
      name: "Copying Avenmoor Holdings (Demo) to a sandbox",
    });
    expect(progress).toBeTruthy();
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("reset modal options", async () => {
    const resets: unknown[] = [];
    serve([]);
    server.use(
      http.post(apiUrl("/api/v1/tenant/reset"), async ({ request }) => {
        resets.push(await request.json());
        return HttpResponse.json(
          {
            ...job("QUEUED"),
            kind: "SANDBOX_RESET",
            mode: null,
            sandbox_tenant_id: NEW_SANDBOX_ID,
          },
          {
            status: 202,
            headers: {
              Location: `/api/v1/jobs/${JOB_ID}`,
              "X-Erev-Sandbox-Tenant-Id": NEW_SANDBOX_ID,
            },
          },
        );
      }),
      http.get(apiUrl(`/api/v1/jobs/${JOB_ID}`), () =>
        HttpResponse.json({ ...job("RUNNING"), kind: "SANDBOX_RESET", mode: null }),
      ),
      http.get(apiUrl("/api/v1/session"), () => HttpResponse.json(SANDBOX_SESSION)),
    );
    renderSandbox(marcus({ active_membership_id: COPY.membership_id }), SANDBOX_SESSION);

    expect(
      await screen.findByText(
        "This workspace is a sandbox copied from Avenmoor Holdings (Demo) as known at 12 Sep 2026 18:10 UTC.",
      ),
    ).toBeTruthy();
    // A sandbox copies nothing: no create control and no tables.
    expect(screen.queryByRole("button", { name: "Create sandbox copy" })).toBeNull();
    expect(screen.queryByRole("table")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: "Reset sandbox" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Reset sandbox" });
    expect(document.activeElement).toBe(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(
      within(dialog).getByText(
        "The current sandbox is archived and a new sandbox replaces it. No data is deleted.",
      ),
    ).toBeTruthy();
    const back = within(dialog).getByRole("radio", {
      name: "Back to the copy taken on 12 Sep 2026 18:10 UTC",
    });
    const empty = within(dialog).getByRole("radio", { name: "Empty workspace" });
    expect((back as HTMLInputElement).checked).toBe(true);
    expect((empty as HTMLInputElement).checked).toBe(false);
    const reason = within(dialog).getByRole("textbox", { name: "Reason (required)" });
    expect(within(dialog).getByText("Minimum 10 characters")).toBeTruthy();

    // SB-R-05: a reason of at least 10 characters.
    const confirm = within(dialog).getByRole("button", { name: "Reset sandbox" });
    fireEvent.change(reason, { target: { value: "too short" } });
    fireEvent.click(confirm);
    expect(await within(dialog).findByText("Enter at least 10 characters.")).toBeTruthy();
    expect(resets).toEqual([]);

    fireEvent.click(empty);
    fireEvent.click(back);
    fireEvent.change(reason, { target: { value: "Rehearsal complete" } });
    fireEvent.click(confirm);
    await waitFor(() => {
      expect(resets).toEqual([{ mode: "SNAPSHOT", reason: "Rehearsal complete" }]);
    });
    expect(
      await screen.findByRole("progressbar", {
        name: "Resetting sandbox Avenmoor pre-close snapshot (Sandbox)",
      }),
    ).toBeTruthy();
    // One reset at a time: the control gives way to the progress.
    expect(screen.queryByRole("button", { name: "Reset sandbox" })).toBeNull();
  });

  it("empty state copy", async () => {
    serve([]);
    renderSandbox(marcus({ memberships: [PRODUCTION] }));

    const empty = await screen.findByTestId("SF-15-empty-sandboxes");
    expect(within(empty).getByRole("heading", { name: "No sandbox copies" })).toBeTruthy();
    expect(
      within(empty).getByText(
        "Copy this workspace to rehearse a close, test a policy change or train users without touching production.",
      ),
    ).toBeTruthy();
    expect(within(empty).getByRole("button", { name: "Create sandbox copy" })).toBeTruthy();
    expect(screen.getAllByRole("button", { name: "Create sandbox copy" })).toHaveLength(2);
    expect(screen.queryByRole("table")).toBeNull();
    expect(
      screen.getByText(
        "A sandbox copy is a separate workspace. Nothing in a sandbox posts or exports, and production is never overwritten.",
      ),
    ).toBeTruthy();
  });

  it("Create sandbox copy sends the name, the purpose and the instant of Now, runs step-up when asked and shows the job until Sandbox <name> is ready.", async () => {
    const requests: { readonly key: string | null; readonly body: Record<string, unknown> }[] = [];
    const opened: unknown[] = [];
    let verified = false;
    let state = "RUNNING";
    serve([]);
    server.use(
      http.post(apiUrl("/api/v1/tenant/snapshots"), async ({ request }) => {
        requests.push({
          key: request.headers.get("Idempotency-Key"),
          body: (await request.json()) as Record<string, unknown>,
        });
        if (!verified) {
          return HttpResponse.json(
            {
              type: "https://erev.dev/problems/mfa-step-up-required",
              title: "Confirm with your authenticator",
              status: 403,
              detail: "Enter a code from your authenticator to continue.",
            },
            { status: 403, headers: { "Content-Type": "application/problem+json" } },
          );
        }
        return HttpResponse.json(
          { ...job("RUNNING"), mode: "export", tenant_snapshot_id: COPY_ID },
          { status: 202, headers: { Location: `/api/v1/jobs/${JOB_ID}` } },
        );
      }),
      http.post(apiUrl("/api/v1/session/mfa"), () => {
        verified = true;
        return HttpResponse.json(PRODUCTION_SESSION);
      }),
      http.get(apiUrl(`/api/v1/jobs/${JOB_ID}`), () =>
        HttpResponse.json(
          state === "RUNNING"
            ? { ...job("RUNNING"), mode: "export" }
            : {
                ...job("SUCCEEDED", {
                  href: `/api/v1/tenant/snapshots/${COPY_ID}`,
                  counts: { derived_mismatches: 0 },
                  sandbox_tenant_id: NEW_SANDBOX_ID,
                }),
                mode: "export",
              },
        ),
      ),
      http.post(apiUrl("/api/v1/session/tenant"), async ({ request }) => {
        opened.push(await request.json());
        return HttpResponse.json(SANDBOX_SESSION);
      }),
    );
    renderSandbox(marcus({ memberships: [PRODUCTION] }));

    const before = Date.now();
    const [create] = await screen.findAllByRole("button", { name: "Create sandbox copy" });
    if (create === undefined) {
      throw new Error("no Create sandbox copy control");
    }
    fireEvent.click(create);
    const dialog = await screen.findByRole("dialog", { name: "Create sandbox copy" });
    expect(
      within(dialog).getByText(
        "The copy includes reference data, events, versions and memberships as known at the chosen time. Derived figures are recomputed in the sandbox.",
      ),
    ).toBeTruthy();
    const knownAt = within(dialog).getByRole("radiogroup", { name: "Known at" });
    expect(within(knownAt).getByRole("radio", { name: "Now" }).getAttribute("aria-checked")).toBe(
      "true",
    );
    expect(within(knownAt).getByRole("radio", { name: "A specific time" })).toBeTruthy();
    const submit = within(dialog).getByRole("button", { name: "Create sandbox copy" });
    fireEvent.click(submit);
    expect(await within(dialog).findByText("Enter a name.")).toBeTruthy();
    expect(requests).toEqual([]);

    fireEvent.change(within(dialog).getByRole("textbox", { name: "Name" }), {
      target: { value: "Avenmoor pre-close snapshot" },
    });
    fireEvent.click(submit);
    // SCR-PERM-05 (ACT-50): the server asks for a fresh code; the same intent is sent again.
    const stepUp = await screen.findByRole("dialog", { name: "Confirm with your authenticator" });
    fireEvent.change(within(stepUp).getByRole("textbox", { name: "Authentication code" }), {
      target: { value: "123456" },
    });
    fireEvent.click(within(stepUp).getByRole("button", { name: "Confirm" }));
    await waitFor(() => {
      expect(requests).toHaveLength(2);
    });
    expect(requests[0]?.key).toBe(requests[1]?.key);
    const body = requests[1]?.body ?? {};
    expect(body.purpose).toBe("SANDBOX_COPY");
    expect(body.name).toBe("Avenmoor pre-close snapshot");
    expect(String(body.known_at)).toMatch(/Z$/);
    const sent = instantMs(String(body.known_at));
    expect(sent).toBeGreaterThanOrEqual(before);
    expect(sent).toBeLessThanOrEqual(Date.now());

    expect(
      await screen.findByRole("progressbar", {
        name: "Copying Avenmoor Holdings (Demo) to a sandbox",
      }),
    ).toBeTruthy();
    // No empty state while the first copy runs.
    expect(screen.queryByTestId("SF-15-empty-sandboxes")).toBeNull();

    state = "SUCCEEDED";
    expect(
      await screen.findByText("Sandbox Avenmoor pre-close snapshot is ready.", undefined, {
        timeout: 5_000,
      }),
    ).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Open sandbox" }));
    await waitFor(() => {
      expect(opened).toEqual([{ tenant_id: NEW_SANDBOX_ID }]);
    });
  });

  it("a copy that fails shows the SCR-ST-12 banner with the refusal's own words; one that ends with determinism mismatches shows the IMP-45 warning", async () => {
    let answer: Record<string, unknown> = {
      ...job("FAILED"),
      problem: {
        type: "https://erev.dev/problems/precondition-failed",
        title: "Record changed",
        status: 412,
        detail: ERR_77,
        instance: `/api/v1/jobs/${JOB_ID}`,
        code: null,
        errors: [
          { field: null, sheet: null, row: null, rule_id: "RETENTION_UNSET", message: ERR_77 },
        ],
      },
    };
    serve();
    server.use(
      http.post(apiUrl("/api/v1/tenant/sandboxes"), () =>
        HttpResponse.json(
          { ...job("QUEUED"), sandbox_tenant_id: NEW_SANDBOX_ID },
          { status: 202, headers: { Location: `/api/v1/jobs/${JOB_ID}` } },
        ),
      ),
      http.get(apiUrl(`/api/v1/jobs/${JOB_ID}`), () => HttpResponse.json(answer)),
    );
    const restore = async (name: string) => {
      const stored = await screen.findByRole("table", { name: "Stored snapshots" });
      const backup = within(stored).getByTestId(`SF-15-row-snapshot-${BACKUP_ID}`);
      fireEvent.click(within(backup).getByRole("button", { name: /Restore/ }));
      const dialog = await screen.findByRole("dialog", { name: "Restore into a new sandbox" });
      fireEvent.change(within(dialog).getByRole("textbox", { name: "Name" }), {
        target: { value: name },
      });
      fireEvent.click(within(dialog).getByRole("button", { name: "Restore into a new sandbox" }));
    };
    renderSandbox();

    await restore("Refused restore");
    expect(
      await screen.findByText(
        "Copying Avenmoor Holdings (Demo) to a sandbox failed. Nothing was committed.",
      ),
    ).toBeTruthy();
    expect(screen.getByText("Reference 9f9f9f9f.")).toBeTruthy();
    // PRD ERR-77 in the banner, in place of the 412's general title.
    expect(screen.getByText(ERR_77)).toBeTruthy();
    expect(screen.queryByText("Record changed")).toBeNull();
    expect(screen.queryByText("Sandbox Refused restore is ready.")).toBeNull();
    cleanup();

    answer = job("SUCCEEDED", {
      href: `/api/v1/tenant/snapshots/${BACKUP_ID}`,
      counts: { derived_mismatches: 2 },
      sandbox_tenant_id: NEW_SANDBOX_ID,
    });
    renderSandbox();
    await restore("Differing restore");
    const warning = await screen.findByTestId("SF-15-banner-determinism");
    expect(
      within(warning).getByText(
        "Recomputing 2 contracts in the sandbox produced results that differ from the source workspace. Review them before relying on the sandbox copy.",
      ),
    ).toBeTruthy();
    expect(await screen.findByText("Sandbox Differing restore is ready.")).toBeTruthy();
  });

  it("a first copy that fails keeps its banner and gives the empty state back under it; the failed snapshot's missing digest is a plain placeholder", async () => {
    let state = "RUNNING";
    let stored: readonly Snapshot[] = [];
    const refused = {
      type: "https://erev.dev/problems/precondition-failed",
      title: "Record changed",
      status: 412,
      detail: ERR_77,
      instance: `/api/v1/jobs/${JOB_ID}`,
      code: null,
      errors: [
        { field: null, sheet: null, row: null, rule_id: "RETENTION_UNSET", message: ERR_77 },
      ],
    };
    const me = marcus({ memberships: [PRODUCTION] });
    serve([]);
    server.use(
      // The ended job asks for the memberships and the snapshots again.
      http.get(apiUrl("/api/v1/me"), () => HttpResponse.json(me)),
      http.get(apiUrl("/api/v1/tenant/snapshots"), () =>
        HttpResponse.json({ items: stored, next_cursor: null }),
      ),
      http.post(apiUrl("/api/v1/tenant/snapshots"), () =>
        HttpResponse.json(
          { ...job("RUNNING"), mode: "export", tenant_snapshot_id: COPY_ID },
          { status: 202, headers: { Location: `/api/v1/jobs/${JOB_ID}` } },
        ),
      ),
      http.get(apiUrl(`/api/v1/jobs/${JOB_ID}`), () =>
        HttpResponse.json(
          state === "RUNNING"
            ? { ...job("RUNNING"), mode: "export" }
            : { ...job("FAILED"), mode: "export", problem: refused },
        ),
      ),
    );
    renderSandbox(me);

    const empty = await screen.findByTestId("SF-15-empty-sandboxes");
    fireEvent.click(within(empty).getByRole("button", { name: "Create sandbox copy" }));
    const dialog = await screen.findByRole("dialog", { name: "Create sandbox copy" });
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Name" }), {
      target: { value: "Avenmoor pre-close snapshot" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create sandbox copy" }));
    expect(
      await screen.findByRole("progressbar", {
        name: "Copying Avenmoor Holdings (Demo) to a sandbox",
      }),
    ).toBeTruthy();
    // While the copy runs its progress stands where the empty state stood.
    expect(screen.queryByTestId("SF-15-empty-sandboxes")).toBeNull();

    stored = [
      snapshot({ id: COPY_ID, status: "FAILED", manifest_file_id: null, manifest_sha256: null }),
      snapshot({ id: BACKUP_ID, purpose: "STORED_BACKUP" }),
    ];
    state = "FAILED";
    expect(await screen.findByText(ERR_77, undefined, { timeout: 5_000 })).toBeTruthy();
    // No sandbox came of it: the workspace has no copies, and says so again, under the banner.
    const again = await screen.findByTestId("SF-15-empty-sandboxes");
    expect(within(again).getByText("No sandbox copies")).toBeTruthy();
    expect(within(again).getByRole("button", { name: "Create sandbox copy" })).toBeTruthy();
    expect(
      screen.getByRole("heading", {
        name: "Copying Avenmoor Holdings (Demo) to a sandbox failed. Nothing was committed.",
      }),
    ).toBeTruthy();

    // The digest is set in the mono face; the placeholder of a snapshot without one is not.
    const table = await screen.findByRole("table", { name: "Stored snapshots" });
    const digest = (id: string) => {
      const cell = within(within(table).getByTestId(`SF-15-row-snapshot-${id}`)).getAllByRole(
        "cell",
      )[4];
      if (cell === undefined) {
        throw new Error("no Manifest SHA-256 cell");
      }
      return { text: cell.textContent, mono: cell.classList.contains("font-mono") };
    };
    expect(digest(BACKUP_ID)).toEqual({ text: digestPrefix(MANIFEST), mono: true });
    expect(digest(COPY_ID)).toEqual({ text: "—", mono: false });
    const failedRow = within(table).getByTestId(`SF-15-row-snapshot-${COPY_ID}`);
    expect(within(failedRow).queryByRole("button")).toBeNull(); // nothing to restore from
  });

  it("a reset ends when the session is in the successor: every cached read is dropped and the page is the successor's", async () => {
    // Reset to an empty workspace: the successor differs from the sandbox it supersedes in what the
    // page says of it, so a page that kept the superseded sandbox's answers is told apart.
    const resets: unknown[] = [];
    const successor = membership("7a7a7a7a-7a7a-4a7a-8a7a-7a7a7a7a7a7a", {
      id: NEW_SANDBOX_ID,
      display_name: "Avenmoor pre-close snapshot (Sandbox)",
      source_known_at: null,
    });
    const moved = signedInSession({
      active_tenant: {
        id: NEW_SANDBOX_ID,
        code: "avenmoor-pre-close-snapshot-r3e3e3e",
        display_name: "Avenmoor pre-close snapshot (Sandbox)",
        kind: "sandbox",
      },
    });
    let sessionReads = 0;
    let meReads = 0;
    serve([]);
    server.use(
      http.post(apiUrl("/api/v1/tenant/reset"), async ({ request }) => {
        resets.push(await request.json());
        return HttpResponse.json(
          {
            ...job("QUEUED"),
            kind: "SANDBOX_RESET",
            mode: null,
            sandbox_tenant_id: NEW_SANDBOX_ID,
          },
          {
            status: 202,
            headers: {
              Location: `/api/v1/jobs/${JOB_ID}`,
              "X-Erev-Sandbox-Tenant-Id": NEW_SANDBOX_ID,
            },
          },
        );
      }),
      // The job stays in the sandbox that was superseded: the moved session no longer sees it.
      http.get(apiUrl(`/api/v1/jobs/${JOB_ID}`), () =>
        HttpResponse.json(
          { type: "https://erev.dev/problems/not-found", title: "Not found", status: 404 },
          { status: 404, headers: { "Content-Type": "application/problem+json" } },
        ),
      ),
      http.get(apiUrl("/api/v1/session"), () => {
        sessionReads += 1;
        return HttpResponse.json(moved);
      }),
      http.get(apiUrl("/api/v1/me"), () => {
        meReads += 1;
        return HttpResponse.json(
          marcus({
            memberships: [
              PRODUCTION,
              successor,
              { ...COPY, tenant: { ...COPY.tenant, status: "ARCHIVED" } },
            ],
            active_membership_id: successor.membership_id,
          }),
        );
      }),
    );
    renderSandbox(marcus({ active_membership_id: COPY.membership_id }), SANDBOX_SESSION);

    const copied =
      "This workspace is a sandbox copied from Avenmoor Holdings (Demo) as known at 12 Sep 2026 18:10 UTC.";
    expect(await screen.findByText(copied)).toBeTruthy();
    fireEvent.click(await screen.findByRole("button", { name: "Reset sandbox" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Reset sandbox" });
    fireEvent.click(within(dialog).getByRole("radio", { name: "Empty workspace" }));
    fireEvent.change(within(dialog).getByRole("textbox", { name: "Reason (required)" }), {
      target: { value: "Rehearsal complete" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Reset sandbox" }));

    expect(
      await screen.findByText(
        "Completed: Resetting sandbox Avenmoor pre-close snapshot (Sandbox).",
        undefined,
        { timeout: 5_000 },
      ),
    ).toBeTruthy();
    expect(resets).toEqual([{ mode: "EMPTY", reason: "Rehearsal complete" }]);
    await waitFor(() => {
      expect(meReads).toBeGreaterThan(0);
    });
    expect(sessionReads).toBeGreaterThan(0);
    // The page is the successor's, read again without a reload: an empty sandbox says so, the
    // superseded sandbox's line is gone, and the reset control is back.
    expect(
      await screen.findByText(
        "This workspace is an empty sandbox of Avenmoor Holdings (Demo).",
        undefined,
        { timeout: 5_000 },
      ),
    ).toBeTruthy();
    expect(screen.queryByText(copied)).toBeNull();
    expect(screen.queryByRole("progressbar")).toBeNull();
    // ...and its reset has no copy to go back to.
    fireEvent.click(await screen.findByRole("button", { name: "Reset sandbox" }));
    const again = await screen.findByRole("alertdialog", { name: "Reset sandbox" });
    expect(
      within(again)
        .getAllByRole("radio")
        .map((radio) => radio.getAttribute("aria-label") ?? radio.parentElement?.textContent),
    ).toEqual(["Empty workspace"]);
  });

  it("A specific time is typed as a journal cut-off is: a UTC instant that has passed, never empty", () => {
    const now = instantMs("2026-09-13T08:00:00Z");
    expect(specificTime("2026-09-12 18:10", now)).toEqual({
      value: "2026-09-12T18:10:00Z",
      error: null,
    });
    expect(specificTime("", now)).toEqual({
      value: null,
      error: "Enter a time as YYYY-MM-DD HH:mm in UTC.",
    });
    expect(specificTime("12 Sep 2026", now).error).toBe("Enter a time as YYYY-MM-DD HH:mm in UTC.");
    expect(specificTime("2026-09-13 09:00", now)).toEqual({
      value: null,
      error: "Enter a time that is not in the future.",
    });
  });

  it("a member without tenant.snapshot sees the access empty state and no request for the snapshots is sent", async () => {
    let asked = 0;
    serve();
    server.use(
      http.get(apiUrl("/api/v1/tenant/snapshots"), () => {
        asked += 1;
        return HttpResponse.json({ items: [], next_cursor: null });
      }),
    );
    renderSandbox(marcus({ permissions: ["contract.read"] }));

    expect(
      await screen.findByRole("heading", { name: "You do not have access to Sandbox copies" }),
    ).toBeTruthy();
    expect(accessDescription()).toBe(
      "Ask a workspace administrator for a role that includes creating sandbox copies (tenant.snapshot).",
    );
    expect(screen.queryByRole("button", { name: "Create sandbox copy" })).toBeNull();
    expect(asked).toBe(0);
  });

  // W-12e: a copy is a copy of the whole workspace. A holder of tenant.snapshot for one entity was
  // shown "No sandbox copies" and "Create sandbox copy" while the API refused the list and the command.
  it("tenant.snapshot for one entity alone: the page says that sandbox copies cover every entity, and no request for the snapshots is sent", async () => {
    let asked = 0;
    serve();
    server.use(
      http.get(apiUrl("/api/v1/tenant/snapshots"), () => {
        asked += 1;
        return HttpResponse.json({ items: [], next_cursor: null });
      }),
    );
    renderSandbox(
      marcus({
        permissions: ["tenant.snapshot", "sandbox.reset"],
        permission_scopes: {
          "tenant.snapshot": ["0a1b2c3d-4e5f-4a6b-8c7d-0000000000de"],
          "sandbox.reset": ["0a1b2c3d-4e5f-4a6b-8c7d-0000000000de"],
        },
      }),
    );

    expect(
      await screen.findByRole("heading", { name: "You do not have access to Sandbox copies" }),
    ).toBeTruthy();
    expect(accessDescription()).toBe(
      "Sandbox copies cover every entity of the workspace. Ask a workspace administrator for a role that includes creating sandbox copies (tenant.snapshot) for all entities.",
    );
    expect(screen.queryByRole("button", { name: "Create sandbox copy" })).toBeNull();
    expect(screen.queryByText("No sandbox copies")).toBeNull();
    expect(asked).toBe(0);
  });

  // W-12e: a reset replaces the whole sandbox, and `POST /tenant/reset` asks sandbox.reset for all
  // entities. A holder for one entity was offered "Reset sandbox" and refused.
  it("sandbox.reset for one entity alone: Reset sandbox is not offered in a sandbox", async () => {
    serve([]);
    server.use(http.get(apiUrl("/api/v1/session"), () => HttpResponse.json(SANDBOX_SESSION)));
    renderSandbox(
      marcus({
        active_membership_id: COPY.membership_id,
        permission_scopes: {
          "contract.read": "*",
          "tenant.snapshot": "*",
          "sandbox.reset": ["0a1b2c3d-4e5f-4a6b-8c7d-0000000000de"],
        },
      }),
      SANDBOX_SESSION,
    );

    expect(
      await screen.findByText(
        "This workspace is a sandbox copied from Avenmoor Holdings (Demo) as known at 12 Sep 2026 18:10 UTC.",
      ),
    ).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Reset sandbox" })).toBeNull();
  });

  it("helpers: the sandboxes of a workspace leave out other workspaces' copies and copies still loading; ids and digests shorten", () => {
    const other = membership("6c6c6c6c-6c6c-4c6c-8c6c-6c6c6c6c6c6c", {
      id: "7d7d7d7d-7d7d-4d7d-8d7d-7d7d7d7d7d7d",
      display_name: "Someone else's copy",
      source_tenant_id: "8e8e8e8e-8e8e-4e8e-8e8e-8e8e8e8e8e8e",
    });
    const loading = membership("9a9a9a9a-9a9a-4a9a-8a9a-9a9a9a9a9a9a", {
      id: "abababab-abab-4bab-8bab-abababababab",
      display_name: "Still copying",
      status: "SUSPENDED",
    });
    expect(
      sandboxesOf([PRODUCTION, COPY, ARCHIVED, other, loading], PRODUCTION_ID).map(
        (item) => item.tenant.display_name,
      ),
    ).toEqual(["Avenmoor pre-close snapshot (Sandbox)", "August rehearsal"]);
    expect(idPrefix(COPY_ID)).toBe("5b1e…09ac");
    expect(digestPrefix(MANIFEST)).toBe("a0c4e9d1…7e22");
    expect(digestPrefix(null)).toBe("—");
  });
});

// docs/dev-guide.md DG-FE-06 (item KIT-UNPLACED-ERRORS-1, head 2): a message that names a member no
// field on screen sends was shown nowhere — the time of a copy is asked only for "A specific time", the
// snapshot of a restore and the mode of a reset have no field. What a field shows is not said again.
describe("SF-15:sandbox, a refused command", () => {
  it("Create sandbox copy: the banner lists what no field on screen shows", async () => {
    const notOnScreen = "A copy is taken as of a time that has passed.";
    const atName = "A sandbox of this name exists.";
    serve([]);
    server.use(
      http.post(apiUrl("/api/v1/tenant/snapshots"), () =>
        refusedWith({ known_at: notOnScreen, name: atName }),
      ),
    );
    renderSandbox(marcus({ memberships: [PRODUCTION] }));
    const [create] = await screen.findAllByRole("button", { name: "Create sandbox copy" });
    fireEvent.click(create as HTMLElement);
    const dialog = await screen.findByRole("dialog", { name: "Create sandbox copy" });
    const name = within(dialog).getByRole("textbox", { name: "Name" });
    fireEvent.change(name, { target: { value: "Avenmoor pre-close snapshot" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Create sandbox copy" }));

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + notOnScreen + REFUSAL_REFERENCE);
    expect(describedBy(name)).toContain(atName);
  });

  it("Restore into a new sandbox: the banner lists what the name does not show", async () => {
    const noField = "This snapshot is past its retention.";
    const atName = "A sandbox of this name exists.";
    serve();
    server.use(
      http.post(apiUrl("/api/v1/tenant/sandboxes"), () =>
        refusedWith({ tenant_snapshot_id: noField, name: atName }),
      ),
    );
    renderSandbox();
    const stored = await screen.findByRole("table", { name: "Stored snapshots" });
    const backup = within(stored).getByTestId(`SF-15-row-snapshot-${BACKUP_ID}`);
    fireEvent.click(
      within(backup).getByRole("button", {
        name: `Restore into a new sandbox from snapshot ${idPrefix(BACKUP_ID)}`,
      }),
    );
    const dialog = await screen.findByRole("dialog", { name: "Restore into a new sandbox" });
    const name = within(dialog).getByRole("textbox", { name: "Name" });
    fireEvent.change(name, { target: { value: "September restore" } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Restore into a new sandbox" }));

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + noField + REFUSAL_REFERENCE);
    expect(describedBy(name)).toContain(atName);
  });

  it("Reset sandbox: the banner lists what the reason does not show", async () => {
    const noField = "The copy this sandbox was taken from is gone. Reset to an empty workspace.";
    const atReason = "Say what the reset is for.";
    serve([]);
    server.use(
      http.post(apiUrl("/api/v1/tenant/reset"), () =>
        refusedWith({ mode: noField, reason: atReason }),
      ),
      http.get(apiUrl("/api/v1/session"), () => HttpResponse.json(SANDBOX_SESSION)),
    );
    renderSandbox(marcus({ active_membership_id: COPY.membership_id }), SANDBOX_SESSION);
    fireEvent.click(await screen.findByRole("button", { name: "Reset sandbox" }));
    const dialog = await screen.findByRole("alertdialog", { name: "Reset sandbox" });
    const reason = within(dialog).getByRole("textbox", { name: /^Reason/ });
    fireEvent.change(reason, { target: { value: "Start the close rehearsal again." } });
    fireEvent.click(within(dialog).getByRole("button", { name: "Reset sandbox" }));

    const banner = await within(dialog).findByRole("alert");
    expect(banner.textContent).toBe(REFUSAL_TITLE + noField + REFUSAL_REFERENCE);
    expect(describedBy(reason)).toContain(atReason);
  });
});
