// @vitest-environment jsdom
// DS-CMP-12 (DESIGN_SYSTEM §7.2): an ordered list named Activity whose items carry ISO 8601 UTC `time`
// elements, paged with "Load older activity" rather than infinite scroll, with the audit chain header.
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ArrowsClockwise, CheckCircle, PencilSimple } from "../icons/registry";
import { Timeline, type TimelineEvent } from "./Timeline";

afterEach(() => {
  cleanup();
});

const EVENTS: readonly TimelineEvent[] = [
  {
    id: "e1",
    at: "2026-09-07T14:05:09Z",
    icon: PencilSimple,
    actor: "Maya Chen",
    actorIsPerson: true,
    verb: "changed End date of",
    object: { label: "Platform subscription", to: "/contracts/c1/obligations/o1" },
    comment: "Customer signed the extension.",
    attachments: [{ label: "extension.pdf", href: "/api/v1/files/f1/content" }],
  },
  {
    id: "e2",
    at: "2026-09-07T09:30:00Z",
    icon: ArrowsClockwise,
    actor: "System",
    verb: "recalculated the contract",
  },
  {
    id: "e3",
    at: "2026-09-06T17:45:12Z",
    icon: CheckCircle,
    actor: "Jordan Lee",
    actorIsPerson: true,
    verb: "approved activation",
  },
];

function inRouter(node: ReactNode) {
  return <MemoryRouter>{node}</MemoryRouter>;
}

describe("DS-CMP-12", () => {
  it("renders an ol named Activity whose items hold time datetime in ISO 8601 UTC", () => {
    render(inRouter(<Timeline events={EVENTS} />));
    const list = screen.getByRole("list", { name: "Activity" });
    expect(list.tagName).toBe("OL");
    const items = Array.from(list.children);
    expect(items).toHaveLength(3);
    for (const item of items) {
      expect(item.tagName).toBe("LI");
      const time = item.querySelector("time");
      expect(time?.getAttribute("datetime")).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$/);
    }
    expect(items[0]?.querySelector("time")?.textContent).toBe("07 Sep 2026 14:05:09 UTC");
    expect(
      screen.getAllByRole("heading", { level: 3 }).map((heading) => heading.textContent),
    ).toEqual(["07 Sep 2026", "06 Sep 2026"]);

    const first = within(items[0] as HTMLElement);
    expect(first.getByText("Maya Chen").parentElement?.textContent?.replace(/\s+/g, " ")).toContain(
      "Maya Chen changed End date of Platform subscription",
    );
    expect(first.getByRole("link", { name: "Platform subscription" }).getAttribute("href")).toBe(
      "/contracts/c1/obligations/o1",
    );
    expect(first.getByText("Customer signed the extension.").tagName).toBe("BLOCKQUOTE");
    expect(first.getByRole("link", { name: "extension.pdf" })).toBeTruthy();
    for (const icon of list.querySelectorAll("svg")) {
      expect(icon.getAttribute("aria-hidden")).toBe("true");
    }
  });

  it("Load older activity pages without infinite scroll", () => {
    const onLoadOlder = vi.fn();
    render(inRouter(<Timeline events={EVENTS} hasOlder onLoadOlder={onLoadOlder} />));
    fireEvent.scroll(window);
    fireEvent.scroll(screen.getByRole("list", { name: "Activity" }));
    expect(onLoadOlder).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Load older activity" }));
    expect(onLoadOlder).toHaveBeenCalledTimes(1);
  });

  it("the audit variant header reads Audit chain verified <DD MMM YYYY HH:mm UTC>", () => {
    const { rerender } = render(
      inRouter(
        <Timeline
          events={EVENTS}
          auditChain={{ verifiedAt: "2026-09-07T14:05:00Z", to: "/audit/v1" }}
        />,
      ),
    );
    const link = screen.getByRole("link", { name: "Audit chain verified 07 Sep 2026 14:05 UTC" });
    expect(link.getAttribute("href")).toBe("/audit/v1");

    rerender(
      inRouter(<Timeline events={EVENTS} auditChain={{ failedAtEvent: 1204, to: "/audit/v2" }} />),
    );
    expect(
      screen.getByRole("heading", { name: "Audit chain verification failed at event 1,204" }),
    ).toBeTruthy();
    expect(
      screen.getByRole("link", { name: "View verification details" }).getAttribute("href"),
    ).toBe("/audit/v2");
  });

  it("shows the empty text and posts a comment with Mod Enter", () => {
    const onPostComment = vi.fn();
    render(inRouter(<Timeline events={[]} onPostComment={onPostComment} />));
    expect(
      screen.getByText("No activity yet. Changes, approvals and calculations appear here."),
    ).toBeTruthy();
    expect(screen.queryByRole("list")).toBeNull();

    const comment = screen.getByRole("textbox", { name: "Comment" });
    fireEvent.change(comment, { target: { value: "Reviewed with the controller." } });
    fireEvent.keyDown(comment, { key: "Enter" });
    expect(onPostComment).not.toHaveBeenCalled();
    fireEvent.keyDown(comment, { key: "Enter", metaKey: true });
    expect(onPostComment).toHaveBeenCalledWith("Reviewed with the controller.");
    expect((comment as HTMLTextAreaElement).value).toBe("");
  });
});
