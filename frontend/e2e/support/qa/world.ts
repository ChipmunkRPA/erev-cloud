// What the world holds, read through the API as a member who reads every entity (release candidate
// QA; PROGRESS.md D-99 (7)). The bound checks need, for each kind of record that belongs to one
// legal entity (04 RLS-TE), one record of an entity the member under test does not cover and one of
// the entity she covers: the first must be answered exactly as an id that names nothing is
// (03 REQ-PLT-012; PRD BR-UX-06), the second is the control that shows she could read such a record
// at all. Nothing here is asserted: a kind the world holds no record of is listed with that fact.
import { randomUUID } from "node:crypto";

import { type Api, at, items, text } from "./api";

export const BOOK = "ASC606";
export const SEPTEMBER = "FY2026-P09";
export const AUGUST = "FY2026-P08";
/** PRD WLD-P-02: the months a seed with the close has locked for AVM-US in ASC 606. */
export const CLOSED_KEYS = [1, 2, 3, 4, 5, 6, 7, 8].map(
  (month) => `FY2026-P${String(month).padStart(2, "0")}`,
);

export interface Entity {
  readonly id: string;
  readonly code: string;
  readonly name: string;
  readonly currency: string;
}

export interface ContractRef {
  readonly id: string;
  readonly externalId: string;
  readonly contractNo: string;
  readonly status: string;
  readonly customer: string;
}

/** One kind of record of one entity: where the API reads it and where a screen shows it. */
export interface Probe {
  readonly kind: string;
  /** How a reader names the record: its number or key. */
  readonly label: string;
  /** API paths that read the record or what hangs on it. */
  readonly reads: readonly string[];
  /** Addresses of the screens that show it. */
  readonly screens: readonly string[];
  /** Ids, numbers and keys that name the record and nothing of another entity. */
  readonly words: readonly string[];
}

export interface EntityWorld {
  readonly entity: Entity;
  readonly contracts: readonly ContractRef[];
  readonly probes: readonly Probe[];
  /** Kinds the world holds no record of for this entity. */
  readonly absent: readonly string[];
}

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/;

/** The same path with every id replaced by an id that names nothing. */
export function unknownOf(path: string): string {
  return path
    .split("/")
    .map((segment) => {
      const [name = "", query] = segment.split("?");
      return UUID.test(name) ? `${randomUUID()}${query === undefined ? "" : `?${query}`}` : segment;
    })
    .join("/")
    .replace(
      /([?&][a-z_]+=)[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/g,
      (_, key: string) => `${key}${randomUUID()}`,
    );
}

export async function readEntities(api: Api): Promise<readonly Entity[]> {
  return (await api.list("/api/v1/entities")).map((item) => ({
    id: text(item, "id"),
    code: text(item, "code"),
    name: text(item, "name"),
    currency: text(item, "functional_currency"),
  }));
}

export async function readContracts(api: Api, entity: string): Promise<readonly ContractRef[]> {
  return (await api.list("/api/v1/contracts", { entity })).map((item) => ({
    id: text(item, "id"),
    externalId: text(item, "external_id"),
    contractNo: text(item, "contract_no"),
    status: text(item, "status"),
    customer: text(item, "customer", "name"),
  }));
}

async function first(api: Api, path: string, params: Record<string, string | number | boolean>) {
  const got = await api.get(path, { limit: 5, ...params });
  return got.status === 200 ? items(got.json) : [];
}

/** The id of the period state of an entity, book and period key, or "". */
export async function periodId(api: Api, entity: string, key: string): Promise<string> {
  const periods = await api.list("/api/v1/periods", { entity, book: BOOK });
  return text(
    periods.find((item) => text(item, "period", "period_key") === key),
    "id",
  );
}

/**
 * The records of one entity the bound checks ask for, each found through a list filtered by the
 * entity, as a reader of every entity sees them.
 */
export async function readEntityWorld(api: Api, entity: Entity): Promise<EntityWorld> {
  const probes: Probe[] = [];
  const absent: string[] = [];
  const code = entity.code;
  const contracts = await readContracts(api, code);

  // A contract with obligations and schedule lines: an active one where the entity has any.
  const contract = contracts.find((item) => item.status === "ACTIVE") ?? contracts[0];
  if (contract === undefined) {
    absent.push("contract");
  } else {
    const id = contract.id;
    probes.push({
      kind: "contract",
      label: contract.externalId,
      reads: [
        `/api/v1/contracts/${id}`,
        `/api/v1/contracts/${id}/obligations?book=${BOOK}`,
        `/api/v1/contracts/${id}/schedule?book=${BOOK}`,
        `/api/v1/contracts/${id}/balances?book=${BOOK}`,
        `/api/v1/contracts/${id}/allocation?book=${BOOK}`,
        `/api/v1/contracts/${id}/history`,
        `/api/v1/contracts/${id}/versions`,
        `/api/v1/contracts/${id}/events`,
        `/api/v1/contracts/${id}/modifications`,
        `/api/v1/contracts/${id}/estimates`,
        `/api/v1/contracts/${id}/subledger-lines`,
        `/api/v1/contracts/${id}/activation-checklist`,
        `/api/v1/contracts/${id}/sources`,
        `/api/v1/schedule-lines?contract=${id}&book=${BOOK}`,
        `/api/v1/subledger-lines?contract=${id}&book=${BOOK}`,
        `/api/v1/exceptions?contract=${id}`,
        `/api/v1/event-submissions?contract=${id}`,
        `/api/v1/combination-suggestions?contract=${id}`,
        `/api/v1/judgements?subject_type=contract&subject_id=${id}`,
      ],
      screens: [
        `/contracts/${id}`,
        `/contracts/${id}/obligations`,
        `/contracts/${id}/schedules`,
        `/contracts/${id}/billing`,
        `/contracts/${id}/journals`,
        `/contracts/${id}/modifications`,
        `/contracts/${id}/estimates`,
        `/contracts/${id}/history`,
        `/contracts/${id}/edit`,
        `/contracts/${id}/modifications/new`,
      ],
      words: [id, contract.externalId, contract.contractNo],
    });

    const [obligation] = await first(api, `/api/v1/contracts/${id}/obligations`, { book: BOOK });
    const obligationId = text(obligation, "id");
    if (obligationId === "") {
      absent.push("obligation");
    } else {
      probes.push({
        kind: "obligation",
        label: `${contract.externalId} ${text(obligation, "obligation_key")}`,
        reads: [
          `/api/v1/obligations/${obligationId}`,
          `/api/v1/obligations/${obligationId}/schedule`,
          `/api/v1/obligations/${obligationId}/versions`,
          `/api/v1/obligations/${obligationId}/events`,
        ],
        screens: [`/contracts/${id}/obligations/${obligationId}`],
        words: [obligationId],
      });
    }

    const [line] = await first(api, "/api/v1/schedule-lines", { contract: id, book: BOOK });
    const lineId = text(line, "id");
    if (lineId === "") {
      absent.push("schedule line");
    } else {
      const explain = `/api/v1/explain/schedule_line/${lineId}/amount?period=${text(line, "period", "period_key")}&book=${BOOK}`;
      const explained = await api.get(explain);
      const trace = text(explained.json, "calc_trace_id");
      probes.push({
        kind: "schedule line and its trace",
        label: `${contract.externalId} ${text(line, "period", "name")}`,
        reads: [explain, ...(trace === "" ? [] : [`/api/v1/calc-traces/${trace}`])],
        screens: trace === "" ? [] : [`/trace/${trace}`],
        words: [lineId, ...(trace === "" ? [] : [trace])],
      });
    }

    const [event] = await first(api, `/api/v1/contracts/${id}/events`, {});
    const eventId = text(event, "id");
    if (eventId === "") {
      absent.push("contract event");
    } else {
      probes.push({
        kind: "contract event",
        label: `${contract.externalId} ${text(event, "event_type")}`,
        reads: [`/api/v1/events/${eventId}`],
        screens: [],
        words: [eventId],
      });
    }

    const [posting] = await first(api, "/api/v1/subledger-lines", { contract: id, book: BOOK });
    const postingId = text(posting, "posting_id");
    if (postingId === "") {
      absent.push("subledger posting");
    } else {
      probes.push({
        kind: "subledger posting",
        label: `${contract.externalId} ${text(posting, "period_key")}`,
        reads: [`/api/v1/subledger-postings/${postingId}`],
        screens: [],
        words: [postingId, text(posting, "id")],
      });
    }
  }

  // A judgement record of one of the entity's contracts (04 T-CON-19): the record has no entity of
  // its own, it belongs to its contract's.
  const ofEntity = new Set(contracts.map((item) => item.id));
  const judgement = (await api.list("/api/v1/judgements", {}, 600)).find((item) =>
    ofEntity.has(text(item, "contract_id")),
  );
  const judgementId = text(judgement, "id");
  if (judgementId === "") {
    absent.push("judgement record");
  } else {
    probes.push({
      kind: "judgement record",
      label: text(judgement, "judgement_no"),
      reads: [
        `/api/v1/judgements/${judgementId}`,
        `/api/v1/judgements?subject_type=contract&subject_id=${text(judgement, "contract_id")}`,
      ],
      screens: [],
      words: [judgementId, text(judgement, "judgement_no")],
    });
  }

  const [run] = await first(api, "/api/v1/journal-runs", { entity: code, book: BOOK });
  const runId = text(run, "id");
  if (runId === "") {
    absent.push("journal run");
  } else {
    const batch = text(run, "batches", 0, "id");
    const [journalLine] = await first(api, `/api/v1/journal-runs/${runId}/lines`, {});
    const journalLineId = text(journalLine, "id");
    probes.push({
      kind: "journal run",
      label: text(run, "run_no"),
      reads: [
        `/api/v1/journal-runs/${runId}`,
        `/api/v1/journal-runs/${runId}/summary`,
        `/api/v1/journal-runs/${runId}/lines`,
        `/api/v1/journal-runs/${runId}/entries`,
        `/api/v1/journal-runs/${runId}/batches`,
        ...(batch === "" ? [] : [`/api/v1/journal-batches/${batch}`]),
        ...(journalLineId === "" ? [] : [`/api/v1/journal-lines/${journalLineId}/drill`]),
      ],
      screens: [
        `/journals/runs/${runId}`,
        `/journals/runs/${runId}/lines`,
        `/journals/runs/${runId}/batches`,
      ],
      words: [runId, text(run, "run_no"), ...(batch === "" ? [] : [batch])],
    });
  }

  const [closeRun] = await first(api, "/api/v1/close-runs", { entity: code, book: BOOK });
  const closeRunId = text(closeRun, "id");
  if (closeRunId === "") {
    absent.push("close run");
  } else {
    probes.push({
      kind: "close run",
      label: text(closeRun, "close_run_no"),
      reads: [`/api/v1/close-runs/${closeRunId}`],
      screens: [],
      words: [closeRunId, text(closeRun, "close_run_no")],
    });
  }

  const september = await periodId(api, code, SEPTEMBER);
  if (september === "") {
    absent.push("period");
  } else {
    probes.push({
      kind: "period",
      label: `${code} ${BOOK} ${SEPTEMBER}`,
      reads: [
        `/api/v1/periods/${september}`,
        `/api/v1/periods/${september}/cockpit`,
        `/api/v1/periods/${september}/checklist`,
        `/api/v1/periods/${september}/locks`,
        `/api/v1/periods/${september}/transitions`,
        `/api/v1/exceptions?blocking=${september}`,
      ],
      screens: [
        `/close/${code}/${BOOK}/${SEPTEMBER}`,
        `/close/${code}/${BOOK}/${SEPTEMBER}/close-run`,
        `/close/${code}/${BOOK}/${SEPTEMBER}/journal-preview`,
        `/close/${code}/${BOOK}/${SEPTEMBER}/history`,
        `/close/${code}/${BOOK}/${SEPTEMBER}/reconciliations`,
      ],
      words: [september],
    });
  }

  const [reconciliation] = await first(api, "/api/v1/reconciliations", { entity: code });
  const reconciliationId = text(reconciliation, "id");
  if (reconciliationId === "") {
    absent.push("reconciliation");
  } else {
    const key = text(reconciliation, "period", "period_key");
    probes.push({
      kind: "reconciliation",
      label: text(reconciliation, "reconciliation_no"),
      reads: [
        `/api/v1/reconciliations/${reconciliationId}`,
        `/api/v1/reconciliations/${reconciliationId}/items`,
      ],
      screens:
        key === "" ? [] : [`/close/${code}/${BOOK}/${key}/reconciliations/${reconciliationId}`],
      words: [reconciliationId, text(reconciliation, "reconciliation_no")],
    });
  }

  const [exception] = await first(api, "/api/v1/exceptions", { entity: code });
  const exceptionId = text(exception, "id");
  if (exceptionId === "") {
    absent.push("exception");
  } else {
    probes.push({
      kind: "exception",
      label: text(exception, "exception_no"),
      reads: [`/api/v1/exceptions/${exceptionId}`],
      screens: [`/data/exceptions/${exceptionId}`],
      words: [exceptionId, text(exception, "exception_no")],
    });
  }

  const [adjustment] = await first(api, "/api/v1/manual-adjustments", { entity: code });
  const adjustmentId = text(adjustment, "id");
  if (adjustmentId === "") {
    absent.push("manual adjustment");
  } else {
    probes.push({
      kind: "manual adjustment",
      label: text(adjustment, "adjustment_no"),
      reads: [`/api/v1/manual-adjustments/${adjustmentId}`],
      screens: [],
      words: [adjustmentId, text(adjustment, "adjustment_no")],
    });
  }

  // A request bound to this entity and to no other (04 §16.10 "Entity scope of a request").
  const requests = await first(api, "/api/v1/approvals", { entity: code, limit: 50 });
  const request = requests.find(
    (item) => at(item, "entity_count") === 1 && at(item, "all_entities") !== true,
  );
  const requestId = text(request, "id");
  if (requestId === "") {
    absent.push("approval request");
  } else {
    probes.push({
      kind: "approval request",
      label: text(request, "request_no"),
      reads: [`/api/v1/approvals/${requestId}`],
      screens: [`/approvals/requests/${requestId}`],
      words: [requestId, text(request, "request_no")],
    });
  }

  probes.push({
    kind: "legal entity",
    label: code,
    reads: [`/api/v1/entities/${entity.id}`],
    screens: [],
    words: [entity.id],
  });

  return { entity, contracts, probes, absent };
}

/** A report run over one entity, made by `api`'s member: its id, or "" with the reason. */
export async function makeWaterfallRun(
  api: Api,
  entities: readonly string[] | null,
  from: string,
  to: string,
): Promise<{ readonly id: string; readonly said: string }> {
  const started = await api.send("POST", "/api/v1/report-runs", {
    report_code: "revenue_waterfall",
    parameters: {
      ...(entities === null ? {} : { entity_codes: entities }),
      book: BOOK,
      from_period_key: from,
      to_period_key: to,
    },
    output_format: "JSON",
  });
  if (started.status !== 202) {
    return {
      id: "",
      said: `${String(started.status)} ${started.problem} ${text(started.json, "detail")}`.trim(),
    };
  }
  const id = started.headers["x-erev-report-run-id"] ?? "";
  const state = await api.job(started);
  return { id, said: `202, job ${state}` };
}

/** The rows of a report run, every page of them. */
export async function reportRows(api: Api, runId: string): Promise<readonly unknown[]> {
  return api.list(`/api/v1/report-runs/${runId}/data`);
}
