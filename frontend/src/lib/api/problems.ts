// RFC 9457 problems (04 API-C-05; docs/dev-guide.md DG-FE-04). The slug comes from `type`, the
// request id from `instance`; an unhandled error has `type = "about:blank"` and no slug.
export const PROBLEM_TYPE_PREFIX = "https://erev.dev/problems/";
export const REQUEST_INSTANCE_PREFIX = "urn:erev:request:";
export const PROBLEM_MEDIA_TYPE = "application/problem+json";

export interface ProblemFieldError {
  readonly field: string | null;
  readonly sheet: string | null;
  readonly row: number | null;
  readonly rule_id: string | null;
  readonly message: string;
}

interface ProblemInit {
  readonly type: string;
  readonly slug: string | null;
  readonly title: string;
  readonly status: number;
  readonly detail: string | null;
  readonly code: string | null;
  readonly errors: readonly ProblemFieldError[];
  readonly requestId: string | null;
}

export class ApiProblem extends Error {
  readonly type: string;
  readonly slug: string | null;
  readonly title: string;
  readonly status: number;
  readonly detail: string | null;
  readonly code: string | null;
  readonly errors: readonly ProblemFieldError[];
  readonly requestId: string | null;

  constructor(init: ProblemInit) {
    super(init.detail ?? init.title);
    this.name = "ApiProblem";
    this.type = init.type;
    this.slug = init.slug;
    this.title = init.title;
    this.status = init.status;
    this.detail = init.detail;
    this.code = init.code;
    this.errors = init.errors;
    this.requestId = init.requestId;
  }
}

function text(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function fieldError(value: unknown): ProblemFieldError | null {
  if (typeof value !== "object" || value === null) {
    return null;
  }
  const item = value as Record<string, unknown>;
  return {
    field: text(item.field),
    sheet: text(item.sheet),
    row: typeof item.row === "number" ? item.row : null,
    rule_id: text(item.rule_id),
    message: text(item.message) ?? "",
  };
}

/** Builds an `ApiProblem` from a parsed body; a body that is not a problem keeps `about:blank`. */
export function parseProblem(
  body: unknown,
  response: Pick<Response, "status" | "statusText">,
): ApiProblem {
  const fields = typeof body === "object" && body !== null ? (body as Record<string, unknown>) : {};
  const type = text(fields.type) ?? "about:blank";
  const instance = text(fields.instance);
  const errors = Array.isArray(fields.errors)
    ? fields.errors.map(fieldError).filter((error): error is ProblemFieldError => error !== null)
    : [];
  return new ApiProblem({
    type,
    slug: type.startsWith(PROBLEM_TYPE_PREFIX) ? type.slice(PROBLEM_TYPE_PREFIX.length) : null,
    title: text(fields.title) ?? response.statusText,
    status: typeof fields.status === "number" ? fields.status : response.status,
    detail: text(fields.detail),
    code: text(fields.code),
    errors,
    requestId:
      instance !== null && instance.startsWith(REQUEST_INSTANCE_PREFIX)
        ? instance.slice(REQUEST_INSTANCE_PREFIX.length)
        : null,
  });
}

export function isProblemResponse(response: Response): boolean {
  const media = (response.headers.get("Content-Type") ?? "").split(";", 1)[0] ?? "";
  return media.trim().toLowerCase() === PROBLEM_MEDIA_TYPE;
}

/** Reads the problem of an error response without consuming its body. */
export async function readProblem(response: Response): Promise<ApiProblem> {
  let body: unknown = null;
  if (isProblemResponse(response)) {
    try {
      body = await response.clone().json();
    } catch {
      // A malformed problem body keeps about:blank with the HTTP status.
    }
  }
  return parseProblem(body, response);
}

/**
 * A read the API refuses with 403 (SCREENS §0.6 SCR-PERM-02): the member may not read it, and asking
 * again does not change that. A reader answers it as "nothing to show" — `null` or an empty list —
 * so the region renders what it renders without the permission, not an error with "Retry".
 */
export function isRefused(error: unknown): boolean {
  return error instanceof ApiProblem && error.status === 403;
}

/** Maps problem `errors[]` onto form field names; the first message of a field wins. */
export function fieldErrorsOf(problem: ApiProblem): Readonly<Record<string, string>> {
  const result: Record<string, string> = {};
  for (const error of problem.errors) {
    if (error.field !== null && !(error.field in result)) {
      result[error.field] = error.message;
    }
  }
  return result;
}
