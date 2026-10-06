// @vitest-environment jsdom
// REQ-UX-016 teaching empty states (DESIGN_SYSTEM DS-CMP-23): what belongs here, the next action and a
// sample-dataset link, without illustrations.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EmptyState, sentenceCount } from "./EmptyState";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("REQ-UX-016 teaching empty states", () => {
  it("renders a heading, at most two sentences, one primary action, a sample-dataset link and no img", () => {
    const onImport = vi.fn();
    const { container } = render(
      <EmptyState
        title="No contracts yet"
        description="Contracts arrive from imports, integrations or the API. Start with a template or connect a source."
        action={{ label: "Import contracts", onAction: onImport }}
        link={{ label: "Load the sample SaaS dataset", href: "#sample-dataset" }}
      />,
    );
    expect(screen.getByRole("heading", { level: 2, name: "No contracts yet" })).toBeTruthy();
    expect(sentenceCount(screen.getByText(/^Contracts arrive/).textContent ?? "")).toBe(2);
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(1);
    fireEvent.click(screen.getByRole("button", { name: "Import contracts" }));
    expect(onImport).toHaveBeenCalledTimes(1);
    expect(
      screen.getByRole("link", { name: "Load the sample SaaS dataset" }).getAttribute("href"),
    ).toBe("#sample-dataset");
    expect(container.querySelector("img")).toBeNull();
  });

  // DS-TYP-10, DS-TYP-18: an identifier beside body text is set in mono. The description stays one
  // text of at most two sentences; a full stop inside an identifier ends none.
  it("sets the identifiers its description names in mono, each occurrence, and leaves the text whole", () => {
    const { container } = render(
      <EmptyState
        title="You do not have access to Security"
        description="Security covers every entity of the workspace. Ask for managing settings (settings.manage) or settings.manage.read for all entities."
        identifiers={["settings.manage", "settings.manage.read", "audit.read"]}
      />,
    );
    const paragraph = container.querySelector("p");
    expect(paragraph?.textContent).toBe(
      "Security covers every entity of the workspace. Ask for managing settings (settings.manage) or settings.manage.read for all entities.",
    );
    const codes = Array.from(paragraph?.querySelectorAll("span") ?? []);
    // The longer identifier is not cut at the shorter one it begins with; one that does not occur
    // adds nothing.
    expect(codes.map((code) => code.textContent)).toEqual([
      "settings.manage",
      "settings.manage.read",
    ]);
    expect(codes.every((code) => code.className === "font-mono text-mono")).toBe(true);
  });

  it("a description without identifiers is one text node", () => {
    const { container } = render(
      <EmptyState title="No contracts yet" description="Contracts arrive from imports." />,
    );
    expect(container.querySelector("p")?.childNodes).toHaveLength(1);
    expect(container.querySelector("p span")).toBeNull();
  });

  it("refuses a description longer than two sentences", () => {
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    expect(() =>
      render(<EmptyState title="No journal runs for Sep 2026" description="One. Two. Three." />),
    ).toThrow(/at most two sentences/);
  });
});
