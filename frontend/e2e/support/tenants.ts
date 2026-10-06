// Fresh tenants through the operator CLI (docs/dev-guide.md DG-E2E-12, DG-KRN-TEN-04; PRD E2E-05,
// BR-PLT-01; 03 REQ-PLT-038). `createTenant` runs `backend/.venv/bin/erev tenant create …` through
// `execFile` (no shell) with `EREV_ENV=e2e` and returns the JSON line the command prints; a non-zero
// exit rejects, which fails the calling `beforeAll`. The harness never calls the operator route.
import { execFile } from "node:child_process";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

export const REPO_ROOT = fileURLToPath(new URL("../../..", import.meta.url));
export const EREV_CLI = join(REPO_ROOT, "backend", ".venv", "bin", "erev");

export interface TenantInput {
  readonly code: string;
  readonly name: string;
  readonly reportingCurrency: string;
  readonly demo: boolean;
  readonly admin: string;
}

/** The API-R-54 201 body as the CLI prints it (keys sorted). */
export type CreatedTenant = Readonly<Record<string, unknown>>;

export function tenantCreateArgs(input: TenantInput): string[] {
  return [
    "tenant",
    "create",
    "--code",
    input.code,
    "--name",
    input.name,
    "--reporting-currency",
    input.reportingCurrency,
    ...(input.demo ? ["--demo"] : []),
    "--admin",
    input.admin,
  ];
}

/** The last non-empty stdout line parsed as JSON; the command prints exactly one line. */
export function parseTenantOutput(stdout: string): CreatedTenant {
  const line = stdout
    .split("\n")
    .map((text) => text.trim())
    .filter((text) => text !== "")
    .at(-1);
  if (line === undefined) {
    throw new Error("erev tenant create printed no JSON line");
  }
  return JSON.parse(line) as CreatedTenant;
}

export function createTenant(input: TenantInput): Promise<CreatedTenant> {
  return new Promise((resolve, reject) => {
    execFile(
      EREV_CLI,
      tenantCreateArgs(input),
      { cwd: REPO_ROOT, env: { ...process.env, EREV_ENV: "e2e" }, maxBuffer: 1024 * 1024 },
      (error, stdout, stderr) => {
        if (error !== null) {
          const exit = typeof error.code === "number" ? String(error.code) : "unknown";
          reject(
            new Error(`erev tenant create --code ${input.code} exited ${exit}: ${stderr.trim()}`, {
              cause: error,
            }),
          );
          return;
        }
        try {
          resolve(parseTenantOutput(stdout));
        } catch (parseError) {
          reject(parseError instanceof Error ? parseError : new Error(String(parseError)));
        }
      },
    );
  });
}
