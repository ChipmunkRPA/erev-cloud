// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, expect, it, vi } from "vitest";
import type { ReportDefinition } from "../../../lib/api/queries/reports";
import { ParametersToolbar, toolbarKeys } from "./ParametersToolbar";
import { runParameters, type ReportContext } from "./specs";

const context: ReportContext = {
  entity: "US",
  book: "ASC606",
  periodKey: null,
  periods: [],
  snapshot: null,
  knownAt: null,
  currencyView: null,
};
const definition = {
  code: "contract_sample_pack",
  parameters_schema: {
    type: "object",
    required: ["contract_external_ids"],
    properties: {
      entity_codes: { type: "array" },
      book: { type: "string" },
      known_at: { type: "string" },
      contract_external_ids: { type: "array", items: { type: "string" } },
      from_period_lock_id: { type: "string", format: "uuid" },
      include_zero: { type: "boolean" },
      as_of: { type: "string", format: "date" },
    },
  },
} as unknown as ReportDefinition;
afterEach(cleanup);

it("exposes declared report fields while retaining the separate context controls", () => {
  expect(toolbarKeys(definition)).toEqual([
    "contract_external_ids",
    "from_period_lock_id",
    "include_zero",
    "as_of",
  ]);
});

it("submits user-entered sample identifiers and lock selectors without editing the URL", () => {
  const submit = vi.fn();
  function Form() {
    const [values, setValues] = useState<Record<string, string>>({});
    return (
      <ParametersToolbar
        definition={definition}
        context={context}
        values={values}
        errors={{}}
        timeBands={null}
        onChange={(key, value) => setValues((old) => ({ ...old, [key]: value }))}
        onRun={() => submit(runParameters(definition, context, values))}
      />
    );
  }
  render(<Form />);
  fireEvent.change(screen.getByRole("textbox", { name: /Contract external IDs/ }), {
    target: { value: "C-01, C-02" },
  });
  fireEvent.change(screen.getByRole("textbox", { name: /From period lock ID/ }), {
    target: { value: "saved-lock" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Run report" }));
  expect(submit).toHaveBeenCalledWith({
    entity_codes: ["US"],
    book: "ASC606",
    contract_external_ids: ["C-01", "C-02"],
    from_period_lock_id: "saved-lock",
  });
});

it("does not silently truncate invalid numeric parameters", () => {
  const numeric = {
    ...definition,
    parameters_schema: { properties: { count: { type: "integer" } } },
  };
  expect(runParameters(numeric, context, { count: "12x" }).count).toBe("12x");
  expect(runParameters(numeric, context, { count: "9007199254740993" }).count).toBe(
    "9007199254740993",
  );
  expect(runParameters(numeric, context, { count: "12" }).count).toBe(12);
});
