// Fake outbox reader (05 NTR-05; PRD WLD-U-R4; CFG-17). With `EREV_EMAIL_BACKEND=fake` the api and
// the worker write each message as an RFC 5322 file
// `${EREV_RUN_DIR}/mail/<tenant code>/<UTC timestamp>-<reference>.eml` with a plain 8-bit body, so
// links stay on one line. Specs wait for a message through `expect.poll`, never through a timeout.
import { existsSync, readdirSync, readFileSync } from "node:fs";
import { isAbsolute, join } from "node:path";

import { expect } from "@playwright/test";

import { REPO_ROOT } from "./tenants";

export interface Mail {
  readonly file: string;
  readonly from: string;
  readonly to: string;
  readonly subject: string;
  readonly date: string;
  readonly messageId: string;
  readonly text: string;
}

export interface MailQuery {
  readonly tenant: string;
  readonly to: string;
  readonly subject?: string | RegExp;
  /** Only messages whose file name sorts after this one (an earlier `Mail.file`). */
  readonly after?: string;
}

const TENANT_CODE = /^[a-z0-9]+(-[a-z0-9]+)*$/; // DG-KRN-TEN-03
const ENCODED_WORD = /=\?([^?]+)\?([QqBb])\?([^?]*)\?=/g;

/** The outbox root: `${EREV_RUN_DIR}/mail`, relative paths from the repository root. */
export function mailRoot(): string {
  const runDir = process.env.EREV_RUN_DIR ?? ".run";
  return join(isAbsolute(runDir) ? runDir : join(REPO_ROOT, runDir), "mail");
}

function decodeWord(charset: string, encoding: string, text: string): string {
  const bytes =
    encoding.toUpperCase() === "B"
      ? Buffer.from(text, "base64")
      : Buffer.from(
          text
            .replace(/_/g, " ")
            .replace(/=([0-9A-Fa-f]{2})/g, (_match, hex: string) =>
              String.fromCharCode(Number.parseInt(hex, 16)),
            ),
          "latin1",
        );
  return new TextDecoder(charset).decode(bytes);
}

/** RFC 2047 encoded words in a header value. */
export function decodeHeader(value: string): string {
  return value
    .replace(/\?=\s+=\?/g, "?==?")
    .replace(ENCODED_WORD, (_match, charset: string, encoding: string, text: string) =>
      decodeWord(charset, encoding, text),
    );
}

/** Headers (unfolded, names lowercased) and the 8-bit body of an RFC 5322 message. */
export function parseMail(file: string, raw: string): Mail {
  const normalised = raw.replace(/\r\n/g, "\n");
  const split = normalised.indexOf("\n\n");
  const head = split === -1 ? normalised : normalised.slice(0, split);
  const body = split === -1 ? "" : normalised.slice(split + 2);
  const headers = new Map<string, string>();
  for (const line of head.replace(/\n[ \t]+/g, " ").split("\n")) {
    const colon = line.indexOf(":");
    if (colon > 0) {
      headers.set(
        line.slice(0, colon).trim().toLowerCase(),
        decodeHeader(line.slice(colon + 1).trim()),
      );
    }
  }
  return {
    file,
    from: headers.get("from") ?? "",
    to: headers.get("to") ?? "",
    subject: headers.get("subject") ?? "",
    date: headers.get("date") ?? "",
    messageId: headers.get("message-id") ?? "",
    text: body,
  };
}

/** The messages of a workspace, oldest first (file names start with the UTC timestamp). */
export function listMail(tenant: string): Mail[] {
  if (!TENANT_CODE.test(tenant)) {
    throw new Error(`not a workspace code: ${tenant}`);
  }
  const directory = join(mailRoot(), tenant);
  if (!existsSync(directory)) {
    return [];
  }
  return readdirSync(directory)
    .filter((name) => name.endsWith(".eml"))
    .sort()
    .map((name) => parseMail(name, readFileSync(join(directory, name), "utf8")));
}

/** The newest message that matches the query, or null. */
export function findMail(query: MailQuery): Mail | null {
  const matches = listMail(query.tenant).filter((mail) => {
    if (query.after !== undefined && mail.file <= query.after) {
      return false;
    }
    if (!mail.to.toLowerCase().includes(query.to.toLowerCase())) {
      return false;
    }
    if (query.subject === undefined) {
      return true;
    }
    return typeof query.subject === "string"
      ? mail.subject === query.subject
      : query.subject.test(mail.subject);
  });
  return matches.at(-1) ?? null;
}

/** Waits until a matching message exists and returns it. */
export async function waitForMail(query: MailQuery, timeout = 30_000): Promise<Mail> {
  let found: Mail | null = null;
  await expect
    .poll(
      () => {
        found = findMail(query);
        return found !== null;
      },
      { message: `mail to ${query.to} in ${query.tenant}`, timeout },
    )
    .toBe(true);
  if (found === null) {
    throw new Error(`no mail to ${query.to} in ${query.tenant}`);
  }
  return found;
}

/** The first absolute link in the message whose path starts with `path`. */
export function linkIn(mail: Mail, path: string): string {
  for (const match of mail.text.matchAll(/https?:\/\/[^\s<>"]+/g)) {
    const url = new URL(match[0]);
    if (url.pathname.startsWith(path)) {
      return url.href;
    }
  }
  throw new Error(`no link to ${path} in ${mail.file}`);
}
