// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { afterEach, expect, it, vi } from "vitest";
import type { ReportDefinition } from "../../../lib/api/queries/reports";
import { ParametersToolbar, toolbarKeys } from "./ParametersToolbar";
import { reportViewSearch } from "../run-links";
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
  fireEvent.change(screen.getByRole("textbox", { name: /Earlier close/ }), {
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

it("edits filters as field/value rows and preserves them through saved-report links", async () => {
  const { reportViewSearch } = await import("../run-links");
  const filtered = {
    ...definition,
    parameters_schema: {
      properties: {
        filters: { type: "object", additionalProperties: { type: "string" } },
      },
    },
  };
  const submit = vi.fn();
  function Form() {
    const [values, setValues] = useState<Record<string, string>>({});
    return (
      <ParametersToolbar
        definition={filtered}
        context={context}
        values={values}
        errors={{}}
        timeBands={null}
        onChange={(key, value) => setValues((old) => ({ ...old, [key]: value }))}
        onRun={() => submit(runParameters(filtered, context, values))}
      />
    );
  }
  render(<Form />);
  fireEvent.click(screen.getByRole("button", { name: "Add filter" }));
  expect(screen.getByRole("button", { name: "Run report" }).getAttribute("aria-disabled")).toBe(
    "true",
  );
  fireEvent.change(screen.getByRole("textbox", { name: "Filter 1 field" }), {
    target: { value: "customer_name" },
  });
  fireEvent.change(screen.getByRole("textbox", { name: "Filter 1 value" }), {
    target: { value: "A&B = US" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Run report" }));
  const parameters = { filters: { customer_name: "A&B = US" } };
  expect(submit).toHaveBeenCalledWith(parameters);
  const search = reportViewSearch({ id: "run", parameters, output: null });
  const restored = new URLSearchParams(search).get("p.filters");
  expect(runParameters(filtered, context, { filters: restored ?? "" })).toEqual(parameters);
  fireEvent.click(screen.getByRole("button", { name: "Add filter" }));
  fireEvent.change(screen.getByRole("textbox", { name: "Filter 2 field" }), {
    target: { value: "customer_name" },
  });
  fireEvent.change(screen.getByRole("textbox", { name: "Filter 2 value" }), {
    target: { value: "Other" },
  });
  expect(screen.getByRole("button", { name: "Run report" }).getAttribute("aria-disabled")).toBe(
    "true",
  );
});

it("retains a saved entity subset until the user explicitly changes scope", () => {
  const values = { entity_codes: "US,DE" };
  expect(runParameters(definition, { ...context, entity: null }, values).entity_codes).toEqual([
    "US",
    "DE",
  ]);
  expect(runParameters(definition, { ...context, entity: "UK" }, values).entity_codes).toEqual([
    "UK",
  ]);
  const change = vi.fn();
  render(
    <ParametersToolbar
      definition={definition}
      context={{ ...context, entity: null }}
      values={values}
      errors={{}}
      timeBands={null}
      onChange={change}
      onRun={() => undefined}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Use all permitted entities" }));
  expect(change).toHaveBeenCalledWith("entity_codes", "");
  expect(
    runParameters(definition, { ...context, entity: null }, { entity_codes: "" }).entity_codes,
  ).toBeUndefined();
});

it("edits sourced legacy balances and preserves structured values when reopening a run", () => {
  const adoption = {
    ...definition,
    code: "adoption_bridge",
    parameters_schema: {
      ...definition.parameters_schema,
      required: [],
      properties: { legacy_functional_positions: { type: "array", items: { type: "object" } } },
    },
  } as ReportDefinition;
  let values: Record<string, string> = {};
  function Editor() {
    const [current, setCurrent] = useState<Record<string, string>>({});
    values = current;
    return (
      <ParametersToolbar
        definition={adoption}
        context={context}
        values={current}
        errors={{}}
        timeBands={null}
        onChange={(key, value) => setCurrent({ ...current, [key]: value })}
        onRun={() => {}}
      />
    );
  }
  render(<Editor />);
  fireEvent.click(screen.getByRole("button", { name: "Add legacy carrying balance" }));
  for (const [label, value] of [
    ["Contract external ID", "C-ADOPT"],
    ["Balance date (YYYY-MM-DD)", "2025-12-31"],
    ["Functional currency (ISO code)", "EUR"],
    ["Legacy contract liability", "123.45"],
    ["Source reference", "Trial balance / C-ADOPT"],
  ] as const)
    fireEvent.change(screen.getByLabelText(label), { target: { value } });
  const parameters = runParameters(adoption, context, values);
  expect(parameters.legacy_functional_positions).toEqual([
    {
      contract_external_id: "C-ADOPT",
      as_of: "2025-12-31",
      currency: "EUR",
      contract_liability: "123.45",
      unbilled_receivable: "0.00",
      source_reference: "Trial balance / C-ADOPT",
    },
  ]);
  const search = new URLSearchParams(reportViewSearch({ id: "run", parameters, output: null }));
  expect(JSON.parse(search.get("p.legacy_functional_positions") ?? "null")).toEqual(
    parameters.legacy_functional_positions,
  );
  fireEvent.click(screen.getByRole("button", { name: /Remove.*1/i }));
  expect(runParameters(adoption, context, values).legacy_functional_positions).toBeUndefined();
});
