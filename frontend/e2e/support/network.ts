// Network guard and CSP-violation recorder (docs/dev-guide.md DG-E2E-08; 03 REQ-SEC-008; 05 SAR-20).
// `context.route("**/*")` lets only `127.0.0.1` hosts and `data:` and `blob:` URLs through; any other
// request is aborted and recorded. Every page of the context reports `securitypolicyviolation` events
// and Chromium's CSP console errors. The records of each test are appended to
// `frontend/e2e/.results/network/<project>.jsonl`, so a spec can assert the record of its project.
import { appendFileSync, existsSync, mkdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import type { BrowserContext, TestInfo } from "@playwright/test";

import { normaliseKey, RESULTS_DIR } from "./screens";

export interface BlockedRequest {
  readonly url: string;
  readonly method: string;
  readonly resourceType: string;
}

export interface CspViolation {
  readonly documentURI: string;
  readonly blockedURI: string;
  readonly violatedDirective: string;
  readonly sample: string;
}

export interface NetworkRecord {
  readonly requests: BlockedRequest[];
  readonly cspViolations: CspViolation[];
}

const CSP_BINDING = "__erevRecordCspViolation";
const CSP_CONSOLE = /Content Security Policy/i;

/** DG-E2E-08: only loopback `127.0.0.1` URLs and `data:` and `blob:` URLs are allowed. */
export function allowedUrl(url: string): boolean {
  if (url.startsWith("data:") || url.startsWith("blob:")) {
    return true;
  }
  try {
    return new URL(url).hostname === "127.0.0.1";
  } catch {
    return false;
  }
}

export function emptyRecord(): NetworkRecord {
  return { requests: [], cspViolations: [] };
}

export async function installNetworkGuard(context: BrowserContext): Promise<NetworkRecord> {
  const record = emptyRecord();
  await context.route("**/*", async (route) => {
    const request = route.request();
    if (allowedUrl(request.url())) {
      await route.continue();
      return;
    }
    record.requests.push({
      url: request.url(),
      method: request.method(),
      resourceType: request.resourceType(),
    });
    await route.abort("blockedbyclient");
  });
  await context.exposeBinding(CSP_BINDING, (_source, violation: CspViolation) => {
    record.cspViolations.push(violation);
  });
  await context.addInitScript((binding) => {
    document.addEventListener("securitypolicyviolation", (event) => {
      const report = (window as unknown as Record<string, (value: unknown) => void>)[binding];
      report?.({
        documentURI: event.documentURI,
        blockedURI: event.blockedURI,
        violatedDirective: event.violatedDirective,
        sample: event.sample,
      });
    });
  }, CSP_BINDING);
  context.on("console", (message) => {
    if (message.type() === "error" && CSP_CONSOLE.test(message.text())) {
      record.cspViolations.push({
        documentURI: message.location().url,
        blockedURI: "",
        violatedDirective: "console",
        sample: message.text(),
      });
    }
  });
  return record;
}

function projectFile(project: string): string {
  return join(RESULTS_DIR, "network", `${normaliseKey(project)}.jsonl`);
}

/** Appends a test's record to its project's file (one JSON line per test). */
export function appendProjectRecord(testInfo: TestInfo, record: NetworkRecord): void {
  mkdirSync(join(RESULTS_DIR, "network"), { recursive: true });
  const line = JSON.stringify({ test: testInfo.titlePath.join(" › "), ...record });
  appendFileSync(projectFile(testInfo.project.name), `${line}\n`);
}

/** The combined record of the project's tests appended so far in this run. */
export function readProjectRecord(project: string): NetworkRecord {
  const combined = emptyRecord();
  const file = projectFile(project);
  if (!existsSync(file)) {
    return combined;
  }
  for (const line of readFileSync(file, "utf8").split("\n")) {
    if (line.trim() === "") {
      continue;
    }
    const entry = JSON.parse(line) as NetworkRecord;
    combined.requests.push(...entry.requests);
    combined.cspViolations.push(...entry.cspViolations);
  }
  return combined;
}
