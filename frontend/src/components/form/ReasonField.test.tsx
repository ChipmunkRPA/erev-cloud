// @vitest-environment jsdom
// SB-R-05 (SCREENS_B §0.3; DS-CMP-21): high-risk confirmations take a reason of at least 10 characters.
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it } from "vitest";

import { ReasonField, reasonError } from "./ReasonField";

afterEach(() => {
  cleanup();
});

function Harness() {
  const [value, setValue] = useState("");
  return <ReasonField label="Reason" value={value} onChange={setValue} />;
}

describe("SB-R-05", () => {
  it("9 characters show the minimum error and the help text", () => {
    render(<Harness />);
    expect(screen.getByText("Minimum 10 characters")).toBeTruthy();
    const reason = screen.getByRole("textbox", { name: "Reason" });
    fireEvent.change(reason, { target: { value: "Too short" } });
    expect(screen.getByText("9 characters")).toBeTruthy();
    fireEvent.blur(reason);
    expect(screen.getByText("Enter at least 10 characters.")).toBeTruthy();
    expect(reason.getAttribute("aria-describedby")).toBe("field-reason-error field-reason-help");
    expect(reason.getAttribute("aria-invalid")).toBe("true");
  });

  it("10 characters clear the error", () => {
    render(<Harness />);
    const reason = screen.getByRole("textbox", { name: "Reason" });
    fireEvent.change(reason, { target: { value: "Duplicate." } });
    fireEvent.blur(reason);
    expect(screen.queryByText("Enter at least 10 characters.")).toBeNull();
    expect(reasonError("  Duplicate.  ")).toBeNull();
    expect(reasonError("Too short")).toBe("Enter at least 10 characters.");
  });

  it("a hint stands before the minimum in the help that describes the field", () => {
    render(
      <ReasonField
        label="Rationale"
        value=""
        onChange={() => undefined}
        hint="Say what you reviewed."
      />,
    );
    const reason = screen.getByRole("textbox", { name: "Rationale" });
    // One help text, the one `aria-describedby` names: the sentence, then the minimum.
    expect(reason.getAttribute("aria-describedby")).toBe("field-reason-help");
    expect(document.getElementById("field-reason-help")?.textContent).toBe(
      "Say what you reviewed. Minimum 10 characters",
    );
    cleanup();

    // Without a hint the help is the minimum alone, as before.
    render(<Harness />);
    expect(document.getElementById("field-reason-help")?.textContent).toBe("Minimum 10 characters");
  });
});
