// @vitest-environment jsdom
import { cleanup, fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, expect, it } from "vitest";
import { registerCurrencies } from "../../../lib/format";
import type { Contract } from "../../../lib/api/queries/contracts";
import { renderWithApp } from "../../../test/app";
import { apiUrl, installMswServer, problemResponse, server } from "../../../test/msw";
import { workbenchContract } from "../../../test/workbench";
import { CombinationSplitDrawer } from "./combination-split";

installMswServer();
afterEach(cleanup);
beforeEach(() => registerCurrencies([{ code: "USD", minor_unit: 2 }]));
const contract = workbenchContract({ status: "ACTIVE" }) as unknown as Contract;
const path = `/api/v1/combination-groups/${contract.combination_group.id}`;

function serve(partial = false) {
  server.use(
    http.get(apiUrl(path), () =>
      HttpResponse.json({
        member_count: 2,
        member_contract_ids: partial ? [contract.id] : [contract.id, "b"],
      }),
    ),
    http.get(apiUrl(`/api/v1/contracts/${contract.id}`), () =>
      HttpResponse.json({ ...contract, external_id: "MEMBER-A" }),
    ),
    http.get(apiUrl("/api/v1/contracts/b"), () =>
      HttpResponse.json({ ...contract, id: "b", external_id: "MEMBER-B" }),
    ),
  );
  renderWithApp(<CombinationSplitDrawer contract={contract} onClose={() => undefined} />);
}

it("reads the chosen split and clears stale results after an edit or server refusal", async () => {
  let reads = 0;
  server.use(
    http.get(apiUrl(`${path}/split-preview`), ({ request }) => {
      reads++;
      const url = new URL(request.url);
      expect(url.searchParams.getAll("leave_contract_ids")).toEqual(["b"]);
      expect(url.searchParams.get("book_code")).toBe("ASC606");
      if (reads > 1)
        return problemResponse("validation-failed", 422, "Recompute the combination first.");
      expect(url.searchParams.get("effective_date")).toBe("2026-09-16");
      return HttpResponse.json({
        book_code: "ASC606",
        currency: "USD",
        currency_minor_unit: 2,
        effective_date: "2026-09-16",
        recognized_minor: 10000,
        unrecognized_minor: 20000,
        source_computation_id: "original-source",
        input_sha256: "abc",
        output_sha256: "def",
        members: [
          {
            contract_id: "b",
            contract_key: "MEMBER-B",
            destination: "SINGLETON:MEMBER-B",
            recognized_minor: 10000,
            remaining_before_minor: 15000,
            remaining_after_minor: 20000,
            remaining_ssp: "55/3",
            obligations: [],
          },
        ],
      });
    }),
  );
  serve();
  await waitFor(() => expect(screen.queryByText("Loading combination members…")).toBeNull());
  const input = screen.getByRole("combobox", { name: "Members leaving the combination" });
  fireEvent.focus(input);
  fireEvent.keyDown(input, { key: "ArrowDown" });
  fireEvent.mouseDown(await screen.findByRole("option", { name: "MEMBER-B" }));
  fireEvent.change(screen.getByLabelText("Split effective date"), {
    target: { value: "09/16/2026" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Calculate split allocation" }));
  await screen.findByRole("table");
  expect(screen.getByText("55/3")).toBeTruthy();
  fireEvent.change(screen.getByLabelText("Split effective date"), {
    target: { value: "09/17/2026" },
  });
  expect(screen.queryByRole("table")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Calculate split allocation" }));
  await screen.findByText("Recompute the combination first.");
  expect(screen.queryByRole("table")).toBeNull();
  expect(reads).toBe(2);
});

it("does not offer a partial authorized population for split preview", async () => {
  serve(true);
  await screen.findByText(
    "The complete member list or split preview could not be loaded. Retry or check your access.",
  );
  expect(
    screen
      .getByRole("button", { name: "Calculate split allocation" })
      .getAttribute("aria-disabled"),
  ).toBe("true");
});
