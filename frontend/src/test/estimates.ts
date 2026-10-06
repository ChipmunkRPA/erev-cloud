// The estimates world of the SF-03:estimates tests (SCREENS §8.9; PRD WLD-X-12, WLD-X-16; 04 API-R-32,
// §16.14 estimates): elements and versions as the API answers them, and a stand-in of the estimate
// routes that keeps its rows as the API does. The element list carries the summaries of the current
// and the latest version and no figure; `POST /estimates/{id}/versions` numbers a DRAFT after the
// latest; `PATCH` applies the members it is sent and returns a rejected or withdrawn version to DRAFT;
// `/preview` is a 202 job whose result carries `summary` and stores nothing; `/submit` and
// `/withdraw` move the version and its request; `/discard` voids a DRAFT, which then is no longer the
// latest version of its element (04 §16.14 rev 1.210). A version created with `modification_id` keeps
// it. A suite reads `requests` for what the screen sent.
import { http, HttpResponse, type JsonBodyType } from "msw";

import type { components } from "../lib/api/schema";
import { apiUrl, problemResponse, server } from "./msw";
import { AVM_US, CONTRACT_ID, MAYA_USER, money, PRIYA_USER } from "./workbench";

type Estimate = components["schemas"]["EstimateOut"];
type EstimateVersion = components["schemas"]["EstimateVersionOut"];
type ImpactSummary = components["schemas"]["ImpactSummaryOut"];
type Attachment = components["schemas"]["AttachmentOut"];
type Judgement = components["schemas"]["JudgementOut"];
type Approval = components["schemas"]["ApprovalOut"];
type Job = components["schemas"]["JobOut"];

export const EAC_ID = "e1e1e1e1-e1e1-4e1e-8e1e-e1e1e1e1e1e1";
export const REBATE_ID = "e2e2e2e2-e2e2-4e2e-8e2e-e2e2e2e2e2e2";
export const ESTIMATE_JOB_ID = "c6c6c6c6-c6c6-4c6c-8c6c-c6c6c6c6c6c6";
export const ESTIMATE_APPROVAL_ID = "d7d7d7d7-d7d7-4d7d-8d7d-d7d7d7d7d7d7";
/** The request that approved version 2 of the K-03 `EAC` element. */
export const EAC_V2_APPROVAL_ID = "d6d6d6d6-d6d6-4d6d-8d6d-d6d6d6d6d6d6";
export const NEW_ESTIMATE_ID = "e9e9e9e9-e9e9-4e9e-8e9e-e9e9e9e9e9e9";

/** T-CON-12 row of the K-03 `EAC` element (SCREENS §8.9). */
export function estimateRow(overrides: Partial<Estimate> = {}): Estimate {
  return {
    id: EAC_ID,
    contract_id: CONTRACT_ID,
    portfolio_id: null,
    obligation_id: null,
    obligation_key: null,
    estimate_kind: "EAC",
    element_code: "EAC",
    vc_element_type: null,
    direction: "INCREASE",
    method: "COST_BUILDUP",
    allocation_target: "CONTRACT",
    target_obligation_ids: [],
    target_obligation_keys: [],
    allocation_criteria_evidence: null,
    current_version: null,
    latest_version: null,
    created_by: MAYA_USER,
    created_at: "2026-02-01T09:00:00Z",
    ...overrides,
  };
}

/** T-CON-13 row; `id` defaults to a value made from the estimate and the version number. */
export function versionRow(
  overrides: Partial<EstimateVersion> & Pick<EstimateVersion, "version_no">,
): EstimateVersion {
  const estimateId = overrides.estimate_id ?? EAC_ID;
  const approved = overrides.status === "APPROVED" || overrides.status === "SUPERSEDED";
  return {
    id: `${estimateId.slice(0, -2)}${String(overrides.version_no).padStart(2, "0")}`,
    estimate_id: estimateId,
    status: "DRAFT",
    effective_date: "2026-02-01",
    scenarios: [],
    parameters: {},
    unconstrained_amount: null,
    most_conservative_amount: null,
    constrained_amount: null,
    rate: null,
    expected_total_amount: null,
    expected_quantity: null,
    amortization_months: null,
    currency: "USD",
    constraint_checklist: null,
    rationale: "Bid estimate at contract inception.",
    judgement_record_id: null,
    content_sha256: approved ? "c".repeat(64) : null,
    approval_request_id: null,
    applied_event_ids: [],
    supersedes_version_id: null,
    approver: approved ? PRIYA_USER : null,
    approved_at: approved ? "2026-02-02T10:00:00Z" : null,
    created_by: MAYA_USER,
    created_at: "2026-02-01T09:05:00Z",
    updated_at: "2026-02-01T09:05:00Z",
    row_version: 1,
    ...overrides,
  };
}

/** The record the stand-in's `POST /judgements` creates. */
export const NEW_JUDGEMENT_ID = "7a7a7a7a-7a7a-4a7a-8a7a-7a7a7a7a7a7a";
/** A `CONSTRAINT` record that stands in a world before the screen acts. */
export const CONSTRAINT_RECORD_ID = "7b7b7b7b-7b7b-4b7b-8b7b-7b7b7b7b7b7b";

/**
 * T-CON-19 row of a `CONSTRAINT` record of the `REBATE-DR-01` element: sent for review unless a case
 * says otherwise. `subject_id` is the version the record was written for.
 */
export function constraintRecord(
  subjectId: string,
  overrides: Readonly<Record<string, unknown>> = {},
): Judgement {
  return {
    id: CONSTRAINT_RECORD_ID,
    judgement_no: "JDG-000061",
    topic: "CONSTRAINT",
    subject_type: "estimate_version",
    subject_id: subjectId,
    contract_id: CONTRACT_ID,
    book: null,
    status: "SUBMITTED",
    conclusion: "A significant reversal is not probable.",
    rationale: "The threshold is expected to be met.",
    alternatives_considered: null,
    codification_refs: [],
    questionnaire: { estimate_key: "REBATE-DR-01", remote: false },
    content_sha256: null,
    approval_request_id: null,
    supersedes_id: null,
    reviewer: null,
    reviewed_at: null,
    created_by: PRIYA_USER,
    created_at: "2026-09-30T09:36:00Z",
    updated_at: "2026-09-30T09:36:00Z",
    ...overrides,
  } as Judgement;
}

/** SCREENS §8.9 K-03 `EAC`: version 1 700,000.00, version 2 820,000.00, version 3 850,000.00 pending. */
export function eacVersions(): EstimateVersion[] {
  const figures = (total: string, costs: string, progress: string) => ({
    expected_total_amount: total,
    costs_incurred_to_date: money(costs),
    progress_ratio: progress,
  });
  return [
    versionRow({
      version_no: 3,
      status: "SUBMITTED",
      effective_date: "2026-09-30",
      rationale: "Steel price escalation (supplier notice 24 Sep 2026)",
      approval_request_id: ESTIMATE_APPROVAL_ID,
      ...figures("850000.00", "502000.00", "0.591"),
    }),
    versionRow({
      version_no: 2,
      status: "APPROVED",
      effective_date: "2026-09-10",
      rationale: "Change order CO-07 adds 120,000.00 of cost",
      approval_request_id: EAC_V2_APPROVAL_ID,
      ...figures("820000.00", "502000.00", "0.612"),
    }),
    versionRow({
      version_no: 1,
      status: "SUPERSEDED",
      ...figures("700000.00", "0.00", "0"),
    }),
  ];
}

/**
 * API-S-ImpactSummary of EAC version 3. The progress, the catch-up, the revenue of Sep 2026 and the
 * transaction price are those of SCREENS §8.9 and §6.4 (PRD WLD-X-12); the other members are
 * placeholders of the right shape, not figures of the world.
 */
export const EAC_PREVIEW: ImpactSummary = {
  transaction_price_before: money("1350000.00"),
  transaction_price_after: money("1350000.00"),
  catch_up_total: money("-29169.29"),
  catch_up_by_obligation: [{ obligation_key: "O1", treatment: null, amount: money("-29169.29") }],
  remaining_allocation_before: [{ obligation_key: "O1", amount: money("523800.00") }],
  remaining_allocation_after: [{ obligation_key: "O1", amount: money("552969.29") }],
  revenue_by_period: [
    {
      period_key: "FY2026-P09",
      before: money("226463.41"),
      after: money("197294.12"),
      change: money("-29169.29"),
    },
  ],
  rpo_before: money("523800.00"),
  rpo_after: money("552969.29"),
  rpo_date: "2026-09-30",
  journal_lines: [],
  balances_before: [
    { balance: "contract_liability", amount: money("0.00") },
    { balance: "contract_asset", amount: money("326200.00") },
  ],
  balances_after: [
    { balance: "contract_liability", amount: money("0.00") },
    { balance: "contract_asset", amount: money("297030.71") },
  ],
  progress_before: "0.612",
  progress_after: "0.591",
  replay_from_date: "2026-09-30",
  origin_period_key: null,
  posting_period_key: null,
};

export interface SentRequest {
  readonly method: string;
  readonly path: string;
  readonly body: unknown;
}

export interface EstimateWorld {
  elements: Estimate[];
  /** Versions by estimate id, newest first. */
  versions: Map<string, EstimateVersion[]>;
  attachments: Map<string, Attachment[]>;
  /** Judgement records by the id of their subject, newest first. */
  judgements: Map<string, Judgement[]>;
  /** The ids `GET /judgements/{id}` was asked for, in order. */
  readonly recordReads: string[];
  /** Open `VC_REASSESSMENT_MISSING` items of the contract. */
  exceptions: Record<string, unknown>[];
  /** `result.summary` of the next preview job. */
  preview: ImpactSummary;
  previewEnds: "SUCCEEDED" | "FAILED";
  /**
   * The reader does not hold `contract.read` for every entity of the contract's combination group:
   * a job that succeeded answers `summary` null with `summary_withheld` true (04 API-S-Job `result`
   * rev 1.314).
   */
  previewWithheld: boolean;
  /** The preparer of the version's request, as `GET /approvals/{id}` answers. */
  requestPreparer: typeof MAYA_USER;
  /**
   * Why the request of a WITHDRAWN version is void (E-05 `void_reason`): its preparer withdrew it, or
   * the API voided it because its subject changed after the submission (REQ-PLT-014).
   */
  voidReason: "WITHDRAWN_BY_PREPARER" | "STALE_SUBJECT";
  /**
   * `impact_preview.summary.catch_up_total` of a request, by request id: the dry run the version was
   * submitted with (REQ-PLT-015). A request without an entry answers no preview.
   */
  catchUps: Map<string, string>;
  /** Refusals of the next command of each kind; null answers as the API does. */
  refuse: {
    element: (() => Response) | null;
    create: (() => Response) | null;
    update: (() => Response) | null;
    submit: (() => Response) | null;
    discard: (() => Response) | null;
  };
  readonly requests: SentRequest[];
  readonly sent: (method: string, suffix: string) => readonly SentRequest[];
}

function summaryOf(version: EstimateVersion | undefined): Estimate["current_version"] {
  return version === undefined
    ? null
    : {
        id: version.id,
        version_no: version.version_no,
        status: version.status,
        effective_date: version.effective_date,
        approver: version.approver,
        approved_at: version.approved_at,
      };
}

function withSummaries(world: EstimateWorld, element: Estimate): Estimate {
  const versions = world.versions.get(element.id) ?? [];
  return {
    ...element,
    current_version: summaryOf(versions.find((item) => item.status === "APPROVED")),
    // The highest version number that is not VOIDED (04 §16.14 rev 1.210, item EST-DISCARD-1).
    latest_version: summaryOf(versions.find((item) => item.status !== "VOIDED")),
  };
}

function job(
  id: string,
  state: Job["state"],
  summary: ImpactSummary | null,
  withheld = false,
): Job {
  const ended = state !== "QUEUED" && state !== "RUNNING";
  return {
    id,
    kind: "CONTRACT_COMPUTE",
    mode: "ESTIMATE_PREVIEW",
    state,
    progress: { done: ended ? 1 : 0, total: 1 },
    problem:
      state === "FAILED"
        ? {
            type: "https://erev.dev/problems/engine-error",
            title: "The computation failed",
            status: 500,
            detail: null,
            instance: null,
            errors: [],
          }
        : null,
    result:
      summary === null
        ? null
        : {
            href: "/api/v1/estimate-versions/x",
            counts: { events: 1 },
            ...(withheld ? { summary: null, summary_withheld: true } : { summary }),
          },
    created_by: MAYA_USER,
    created_at: "2026-09-30T09:40:00Z",
    started_at: "2026-09-30T09:40:01Z",
    finished_at: ended ? "2026-09-30T09:40:03Z" : null,
  } as Job;
}

function approval(world: EstimateWorld, version: EstimateVersion, code: string): Approval {
  // 04 E-12 and E-05: a SUBMITTED version waits on a PENDING request, a REJECTED one was refused, and
  // `on_voided` returns the version to WITHDRAWN whoever closed the request — which then reads
  // WITHDRAWN when its preparer withdrew it and VOIDED when the API voided it as stale, each with its
  // `void_reason` (the approvals engine's two closings).
  const status =
    version.status === "SUBMITTED"
      ? "PENDING"
      : version.status === "APPROVED" || version.status === "SUPERSEDED"
        ? "APPROVED"
        : version.status === "REJECTED"
          ? "REJECTED"
          : world.voidReason === "STALE_SUBJECT"
            ? "VOIDED"
            : "WITHDRAWN";
  const closed = status === "VOIDED" || status === "WITHDRAWN";
  const id = version.approval_request_id ?? ESTIMATE_APPROVAL_ID;
  const catchUp = world.catchUps.get(id);
  return {
    id,
    request_no: id === EAC_V2_APPROVAL_ID ? "APR-000412" : "APR-000437",
    status,
    summary: `Approve ${code} version ${String(version.version_no)} of CON-000004`,
    subject: {
      type: "ESTIMATE_VERSION",
      id: version.id,
      display: `Approve ${code} version ${String(version.version_no)} of CON-000004`,
      href: null,
      row_version: null,
      content_sha256: "c70fa4af43b1".padEnd(64, "0"),
    },
    entity: AVM_US,
    // One entity names the request (04 API-S-Approval: `entities`, `entity_count`, `all_entities`).
    entities: [AVM_US],
    entity_count: 1,
    all_entities: false,
    amount: null,
    flags: [],
    attachments: [],
    // 04 API-S-Approval: the stored preview's file and the summary of its before and after members.
    impact_preview:
      catchUp === undefined
        ? null
        : {
            file_id: "f7f7f7f7-f7f7-4f7f-8f7f-f7f7f7f7f7f7",
            sha256: "e".repeat(64),
            summary: {
              revenue_by_period_before: [],
              revenue_by_period_after: [],
              balances_before: [],
              balances_after: [],
              journal_lines: [],
              catch_up_total: money(catchUp),
              criteria_met: null,
            },
          },
    preparer: world.requestPreparer,
    routing: { rule_key: null, rule_set_version_id: null },
    can_decide: false,
    content_withheld: false,
    reason_code: null,
    comment: null,
    current_step_no: 1,
    submitted_at: "2026-09-30T10:00:00Z",
    decided_at: status === "REJECTED" || status === "APPROVED" ? "2026-09-30T10:30:00Z" : null,
    void_reason: closed ? world.voidReason : null,
    voided_at: closed ? "2026-09-30T10:30:00Z" : null,
    steps: [
      {
        step_no: 1,
        name: "Revenue review",
        required_permission: "estimate.approve",
        min_approvers: 1,
        // The open steps of a closed request become VOIDED.
        status: status === "PENDING" ? "ACTIVE" : closed ? "VOIDED" : status,
        decisions: [],
      },
    ],
  } as Approval;
}

const VERSION_MEMBERS = [
  "effective_date",
  "scenarios",
  "parameters",
  "unconstrained_amount",
  "most_conservative_amount",
  "constrained_amount",
  "rate",
  "expected_total_amount",
  "expected_quantity",
  "amortization_months",
  "constraint_checklist",
  "rationale",
  "judgement_record_id",
] as const;

/**
 * Serves the estimate routes of `CONTRACT_ID` over the given elements and versions. Register after
 * `serveWorkbench`: these handlers take precedence over its empty attachment and judgement lists.
 */
export function serveEstimates(
  elements: readonly Estimate[] = [],
  versions: Readonly<Record<string, readonly EstimateVersion[]>> = {},
): EstimateWorld {
  const requests: SentRequest[] = [];
  const world: EstimateWorld = {
    elements: [...elements],
    versions: new Map(Object.entries(versions).map(([id, rows]) => [id, [...rows]])),
    attachments: new Map(),
    judgements: new Map(),
    recordReads: [],
    exceptions: [],
    preview: EAC_PREVIEW,
    previewEnds: "SUCCEEDED",
    previewWithheld: false,
    requestPreparer: MAYA_USER,
    voidReason: "WITHDRAWN_BY_PREPARER",
    // Version 3: SCREENS §8.9 (PRD WLD-X-12). Version 2: a placeholder of the right shape, not a
    // figure of the world.
    catchUps: new Map([
      [ESTIMATE_APPROVAL_ID, "-29169.29"],
      [EAC_V2_APPROVAL_ID, "-41804.88"],
    ]),
    refuse: { element: null, create: null, update: null, submit: null, discard: null },
    requests,
    sent: (method, suffix) =>
      requests.filter((item) => item.method === method && item.path.endsWith(suffix)),
  };
  const log = async (request: Request): Promise<Record<string, unknown>> => {
    const text = await request.text();
    const body = (text === "" ? null : JSON.parse(text)) as Record<string, unknown> | null;
    requests.push({ method: request.method, path: new URL(request.url).pathname, body });
    return body ?? {};
  };
  const find = (versionId: string) => {
    for (const [estimateId, rows] of world.versions) {
      const index = rows.findIndex((item) => item.id === versionId);
      const row = rows[index];
      if (row !== undefined) {
        return { estimateId, rows, index, row };
      }
    }
    return null;
  };
  const replace = (versionId: string, next: EstimateVersion) => {
    const found = find(versionId);
    if (found !== null) {
      const rows = [...found.rows];
      rows[found.index] = next;
      world.versions.set(found.estimateId, rows);
    }
  };
  const list = (items: readonly unknown[]) =>
    HttpResponse.json(
      { items: items as JsonBodyType[], next_cursor: null },
      { headers: { "X-Erev-Total-Count": String(items.length) } },
    );
  const notFound = () => new HttpResponse(null, { status: 404 });
  let jobs = 0;
  let files = 0;

  server.use(
    http.get(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/estimates`), () =>
      list(world.elements.map((element) => withSummaries(world, element))),
    ),
    http.post(apiUrl(`/api/v1/contracts/${CONTRACT_ID}/estimates`), async ({ request }) => {
      const body = await log(request);
      if (world.refuse.element !== null) {
        return world.refuse.element();
      }
      const created = estimateRow({
        id: NEW_ESTIMATE_ID,
        estimate_kind: body.estimate_kind as Estimate["estimate_kind"],
        element_code: String(body.element_code),
        method: body.method as Estimate["method"],
        vc_element_type: (body.vc_element_type as string | null | undefined) ?? null,
        allocation_target: body.allocation_target as Estimate["allocation_target"],
        target_obligation_keys: (body.target_obligation_keys as string[] | undefined) ?? [],
        obligation_key: (body.obligation_key as string | null | undefined) ?? null,
        allocation_criteria_evidence:
          (body.allocation_criteria_evidence as string | null | undefined) ?? null,
      });
      world.elements = [...world.elements, created];
      world.versions.set(created.id, []);
      return HttpResponse.json(created, { status: 201 });
    }),
    http.get(apiUrl("/api/v1/estimates/:estimateId/versions"), ({ params }) =>
      list(world.versions.get(String(params.estimateId)) ?? []),
    ),
    http.post(apiUrl("/api/v1/estimates/:estimateId/versions"), async ({ request, params }) => {
      const body = await log(request);
      if (world.refuse.create !== null) {
        return world.refuse.create();
      }
      const estimateId = String(params.estimateId);
      const rows = world.versions.get(estimateId) ?? [];
      const created = versionRow({
        estimate_id: estimateId,
        version_no: (rows[0]?.version_no ?? 0) + 1,
        supersedes_version_id: rows.find((item) => item.status === "APPROVED")?.id ?? null,
        // T-CON-13: the draft modification the version is created inside, from its INSERT on.
        modification_id: (body.modification_id as string | null | undefined) ?? null,
        ...(Object.fromEntries(
          VERSION_MEMBERS.filter((name) => name in body).map((name) => [name, body[name]]),
        ) as Partial<EstimateVersion>),
        created_at: "2026-09-30T09:30:00Z",
        updated_at: "2026-09-30T09:30:00Z",
      });
      world.versions.set(estimateId, [created, ...rows]);
      return HttpResponse.json(created, { status: 201 });
    }),
    http.get(apiUrl("/api/v1/estimate-versions/:versionId"), ({ params }) => {
      const found = find(String(params.versionId));
      return found === null ? notFound() : HttpResponse.json(found.row);
    }),
    http.patch(apiUrl("/api/v1/estimate-versions/:versionId"), async ({ request, params }) => {
      const body = await log(request);
      if (world.refuse.update !== null) {
        return world.refuse.update();
      }
      const found = find(String(params.versionId));
      if (found === null) {
        return notFound();
      }
      const next: EstimateVersion = {
        ...found.row,
        ...(Object.fromEntries(
          VERSION_MEMBERS.filter((name) => name in body).map((name) => [name, body[name]]),
        ) as Partial<EstimateVersion>),
        status: "DRAFT",
        updated_at: `2026-09-30T09:${String(31 + requests.length).padStart(2, "0")}:00Z`,
        row_version: found.row.row_version + 1,
      };
      replace(found.row.id, next);
      return HttpResponse.json(next);
    }),
    http.post(apiUrl("/api/v1/estimate-versions/:versionId/preview"), async ({ request }) => {
      await log(request);
      jobs += 1;
      const id = `${ESTIMATE_JOB_ID.slice(0, -1)}${String(jobs)}`;
      return HttpResponse.json(job(id, "QUEUED", null), {
        status: 202,
        headers: { Location: `/api/v1/jobs/${id}` },
      });
    }),
    http.get(apiUrl("/api/v1/jobs/:jobId"), ({ params }) =>
      HttpResponse.json(
        job(
          String(params.jobId),
          world.previewEnds,
          world.previewEnds === "SUCCEEDED" ? world.preview : null,
          world.previewWithheld,
        ),
      ),
    ),
    http.post(
      apiUrl("/api/v1/estimate-versions/:versionId/submit"),
      async ({ request, params }) => {
        await log(request);
        if (world.refuse.submit !== null) {
          return world.refuse.submit();
        }
        const found = find(String(params.versionId));
        if (found === null) {
          return notFound();
        }
        const next: EstimateVersion = {
          ...found.row,
          status: "SUBMITTED",
          content_sha256: "c".repeat(64),
          approval_request_id: ESTIMATE_APPROVAL_ID,
        };
        replace(found.row.id, next);
        return HttpResponse.json(next);
      },
    ),
    http.post(
      apiUrl("/api/v1/estimate-versions/:versionId/withdraw"),
      async ({ request, params }) => {
        await log(request);
        const found = find(String(params.versionId));
        if (found === null) {
          return notFound();
        }
        const next: EstimateVersion = { ...found.row, status: "WITHDRAWN" };
        replace(found.row.id, next);
        return HttpResponse.json(next);
      },
    ),
    // 04 §16.14 rev 1.210 (item EST-DISCARD-1): `DRAFT` → `VOIDED`, no body; any other status is
    // refused under the rule id of DB-03.
    http.post(
      apiUrl("/api/v1/estimate-versions/:versionId/discard"),
      async ({ request, params }) => {
        await log(request);
        if (world.refuse.discard !== null) {
          return world.refuse.discard();
        }
        const found = find(String(params.versionId));
        if (found === null) {
          return notFound();
        }
        if (found.row.status !== "DRAFT") {
          return problemResponse("invalid-transition", 409, "Action not available in this state", {
            errors: [
              {
                field: null,
                rule_id: "DB-03",
                message: "Only a draft estimate version can be discarded.",
              },
            ],
          });
        }
        const next: EstimateVersion = { ...found.row, status: "VOIDED" };
        replace(found.row.id, next);
        return HttpResponse.json(next);
      },
    ),
    http.get(apiUrl("/api/v1/approvals/:requestId"), ({ params }) => {
      for (const element of world.elements) {
        const row = (world.versions.get(element.id) ?? []).find(
          (item) => item.approval_request_id === String(params.requestId),
        );
        if (row !== undefined) {
          return HttpResponse.json(approval(world, row, element.element_code));
        }
      }
      // Not the request of an estimate version: another handler of the suite answers it.
      return undefined;
    }),
    http.get(apiUrl("/api/v1/attachments"), ({ request }) => {
      const id = new URL(request.url).searchParams.get("subject_id") ?? "";
      return list(world.attachments.get(id) ?? []);
    }),
    http.post(apiUrl("/api/v1/files"), async ({ request }) => {
      // The multipart body as text: the DOM `File` of this environment is not the parser's.
      const text = await request.text();
      files += 1;
      requests.push({
        method: "POST",
        path: "/api/v1/files",
        body: {
          purpose: /name="purpose"\r\n\r\n([^\r]*)/.exec(text)?.[1] ?? null,
          name: /filename="([^"]*)"/.exec(text)?.[1] ?? null,
        },
      });
      return HttpResponse.json(
        { id: `f0f0f0f0-f0f0-4f0f-8f0f-f0f0f0f0f0${String(files).padStart(2, "0")}` },
        { status: 201 },
      );
    }),
    http.post(apiUrl("/api/v1/attachments"), async ({ request }) => {
      const body = await log(request);
      const subject = String(body.subject_id);
      const fileId = String(body.file_object_id);
      const upload = requests.filter((item) => item.path === "/api/v1/files").at(-1);
      const created = {
        id: `a0a0a0a0-a0a0-4a0a-8a0a-${fileId.slice(-12)}`,
        subject_type: "estimate_version",
        subject_id: subject,
        file_object_id: fileId,
        original_filename: (upload?.body as { name?: string } | undefined)?.name ?? null,
        description: null,
        media_type: "application/pdf",
        size_bytes: 20480,
        sha256: "d".repeat(64),
        created_at: "2026-09-30T09:35:00Z",
        created_by: MAYA_USER.id,
        created_by_kind: "USER",
        voided_at: null,
        voided_by: null,
        voided_by_kind: null,
        void_reason: null,
      } as Attachment;
      world.attachments.set(subject, [created, ...(world.attachments.get(subject) ?? [])]);
      return HttpResponse.json(created, { status: 201 });
    }),
    http.get(apiUrl("/api/v1/judgements"), ({ request }) => {
      const id = new URL(request.url).searchParams.get("subject_id") ?? "";
      return list(world.judgements.get(id) ?? []);
    }),
    // 04 API-R-33 `GET /judgements/{id}`: the record a version names, whatever its subject.
    http.get(apiUrl("/api/v1/judgements/:judgementId"), ({ params }) => {
      world.recordReads.push(String(params.judgementId));
      for (const rows of world.judgements.values()) {
        const row = rows.find((item) => item.id === String(params.judgementId));
        if (row !== undefined) {
          return HttpResponse.json(row);
        }
      }
      return notFound();
    }),
    http.post(apiUrl("/api/v1/judgements"), async ({ request }) => {
      const body = await log(request);
      const subject = String(body.subject_id);
      const created = {
        id: NEW_JUDGEMENT_ID,
        judgement_no: "JDG-000052",
        topic: body.topic,
        subject_type: body.subject_type,
        subject_id: subject,
        // The route defaults no contract for an estimate version: the record names the one it is sent.
        contract_id: (body.contract_id as string | null | undefined) ?? null,
        book: null,
        status: "DRAFT",
        conclusion: body.conclusion,
        rationale: body.rationale,
        alternatives_considered: null,
        codification_refs: [],
        questionnaire: body.questionnaire ?? null,
        content_sha256: null,
        approval_request_id: null,
        supersedes_id: null,
        reviewer: null,
        reviewed_at: null,
        created_by: MAYA_USER,
        created_at: "2026-09-30T09:36:00Z",
        updated_at: "2026-09-30T09:36:00Z",
      } as Judgement;
      world.judgements.set(subject, [created, ...(world.judgements.get(subject) ?? [])]);
      return HttpResponse.json(created, { status: 201 });
    }),
    http.post(apiUrl("/api/v1/judgements/:judgementId/submit"), async ({ request, params }) => {
      await log(request);
      for (const [subject, rows] of world.judgements) {
        const row = rows.find((item) => item.id === String(params.judgementId));
        if (row !== undefined) {
          const next = { ...row, status: "SUBMITTED" } as Judgement;
          world.judgements.set(
            subject,
            rows.map((item) => (item.id === row.id ? next : item)),
          );
          return HttpResponse.json(next);
        }
      }
      return notFound();
    }),
    // 04 API-R-33 `POST /judgements/{id}/discard` (rev 1.242, rev 1.296; PRD SM-10 `DRAFT` →
    // `VOIDED` and, rev 1.199, `REJECTED` → `VOIDED`): a draft or a rejected record is voided and
    // keeps its number; a record in any other status is refused (409), in the route's words.
    http.post(apiUrl("/api/v1/judgements/:judgementId/discard"), async ({ request, params }) => {
      await log(request);
      for (const [subject, rows] of world.judgements) {
        const row = rows.find((item) => item.id === String(params.judgementId));
        if (row !== undefined) {
          if (row.status !== "DRAFT" && row.status !== "REJECTED") {
            return problemResponse(
              "invalid-transition",
              409,
              "Action not available in this state",
              {
                code: null,
                detail: "Only a draft or rejected judgement record can be discarded.",
                errors: [
                  {
                    field: "status",
                    message: "Only a draft or rejected judgement record can be discarded.",
                    row: null,
                    rule_id: "DB-03",
                    sheet: null,
                  },
                ],
              },
            );
          }
          const next = { ...row, status: "VOIDED" } as Judgement;
          world.judgements.set(
            subject,
            rows.map((item) => (item.id === row.id ? next : item)),
          );
          return HttpResponse.json(next);
        }
      }
      return notFound();
    }),
    http.get(apiUrl("/api/v1/exceptions"), () => list(world.exceptions)),
  );
  return world;
}
