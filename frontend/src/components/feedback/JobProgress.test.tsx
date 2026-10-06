// @vitest-environment jsdom
// DS-CMP-24 and REQ-UX-021 (DESIGN_SYSTEM §7.5; SCREENS SCR-ST-12): progress in place, polite completion,
// assertive failure, and a page that stays navigable while the job runs.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { registerLiveRegions } from "../../lib/a11y/announce";
import { JobProgress, type JobProgressJob } from "./JobProgress";

afterEach(() => {
  cleanup();
});

const JOB_ID = "8d4f2e1c-3b5a-4c7d-9e8f-0a1b2c3d4e5f";
// 2026-09-13T09:02:14Z, 2 min 14 s after the job started.
const NOW = 1_789_290_134_000;

function job(
  state: JobProgressJob["state"],
  problem: JobProgressJob["problem"] = null,
): JobProgressJob {
  return {
    id: JOB_ID,
    state,
    progress: { done: 412, total: 1_204 },
    started_at: "2026-09-13T09:00:00Z",
    problem,
  };
}

function liveRegions() {
  const polite = vi.fn();
  const assertive = vi.fn();
  const unregister = registerLiveRegions(polite, assertive);
  return { polite, assertive, unregister };
}

describe("DS-CMP-24 and REQ-UX-021", () => {
  it("shows a progressbar valued 412 of 1,204 contracts with counts and elapsed time", () => {
    render(
      <JobProgress
        label="Recalculating 1,204 contracts"
        job={job("RUNNING")}
        unit="contracts"
        now={NOW}
      />,
    );
    const bar = screen.getByRole("progressbar", { name: "Recalculating 1,204 contracts" });
    expect(bar.getAttribute("aria-valuetext")).toBe("412 of 1,204 contracts");
    expect(bar.getAttribute("aria-valuenow")).toBe("412");
    expect(bar.getAttribute("aria-valuemin")).toBe("0");
    expect(bar.getAttribute("aria-valuemax")).toBe("1204");
    expect(screen.getByText("412 of 1,204")).toBeTruthy();
    expect(screen.getByText("2 min 14 s")).toBeTruthy();
  });

  it("announces completion politely", () => {
    const { polite, assertive, unregister } = liveRegions();
    const { rerender } = render(
      <JobProgress
        label="Close run for US01 Sep 2026"
        job={job("RUNNING")}
        unit="steps"
        now={NOW}
      />,
    );
    rerender(
      <JobProgress
        label="Close run for US01 Sep 2026"
        job={job("SUCCEEDED")}
        unit="steps"
        now={NOW}
        summary={<p>Close run CR-0012 succeeded.</p>}
      />,
    );
    expect(polite).toHaveBeenCalledWith("Completed: Close run for US01 Sep 2026.");
    expect(assertive).not.toHaveBeenCalled();
    expect(screen.queryByRole("progressbar")).toBeNull();
    expect(screen.getByText("Close run CR-0012 succeeded.")).toBeTruthy();
    unregister();
  });

  it("shows the negative failure banner and announces it assertively", () => {
    const { assertive, unregister } = liveRegions();
    const onRetry = vi.fn();
    const problem = { title: "Engine invariant violated" } as NonNullable<
      JobProgressJob["problem"]
    >;
    const { rerender } = render(
      <JobProgress
        label="Calculating journals for US01 Sep 2026"
        job={job("RUNNING")}
        unit="batches"
        now={NOW}
        onRetry={onRetry}
      />,
    );
    rerender(
      <JobProgress
        label="Calculating journals for US01 Sep 2026"
        job={job("FAILED", problem)}
        unit="batches"
        now={NOW}
        onRetry={onRetry}
      />,
    );
    const title = "Calculating journals for US01 Sep 2026 failed. Nothing was committed.";
    expect(screen.getByRole("heading", { name: title })).toBeTruthy();
    expect(screen.getByText("Engine invariant violated")).toBeTruthy();
    expect(screen.getByText("Reference 8d4f2e1c.")).toBeTruthy();
    expect(assertive).toHaveBeenCalledWith(title);
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledTimes(1);
    unregister();
  });

  it("leaves the page navigable while the job runs", () => {
    const onOpen = vi.fn();
    render(
      <main>
        <a href="#contracts">Contracts</a>
        <JobProgress
          label="Verifying the audit chain"
          job={job("RUNNING")}
          unit="events"
          now={NOW}
        />
        <button type="button" onClick={onOpen}>
          Open journal run
        </button>
      </main>,
    );
    expect(document.querySelector("[aria-modal], [inert], dialog")).toBeNull();
    expect(document.body.getAttribute("aria-busy")).toBeNull();
    const other = screen.getByRole("button", { name: "Open journal run" });
    other.focus();
    expect(document.activeElement).toBe(other);
    fireEvent.click(other);
    expect(onOpen).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("progressbar")).toBeTruthy();
  });

  it("an unknown total shows the indeterminate bar", () => {
    render(
      <JobProgress
        label="Copying Avenmoor to a sandbox"
        job={{ ...job("QUEUED"), progress: { done: 0, total: null }, started_at: null }}
        unit="rows"
      />,
    );
    expect(screen.getByRole("progressbar").getAttribute("aria-valuetext")).toBe("In progress");
    expect(screen.getByRole("progressbar").hasAttribute("aria-valuenow")).toBe(false);
  });
});
