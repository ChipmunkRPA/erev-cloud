// DG-FE-06 (docs/dev-guide.md §8.2, rev 1.265; SCREENS §0.7 SCR-ST-13; item KIT-UNPLACED-ERRORS-1, head
// 2): a refused command is shown by `RefusalBanner` of src/components/feedback. `ProblemBanner` of the
// contract drawers said the title, the detail and the messages without a field, and dropped every other
// sentence of `errors[]`; 81 forms in 42 files showed it. It is gone, and it does not come back under
// its name. The drawers' `fieldError`, which read a message by the end of its pointer, has one caller
// left — the estimate element drawer, whose own banner lists what its fields do not show — and the list
// of its callers only shrinks.
import { readdirSync, readFileSync } from "node:fs";
import { relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const FRONTEND = fileURLToPath(new URL("..", import.meta.url));
const SOURCES = resolve(FRONTEND, "src");
/** The module that holds the drawers' `fieldError`. */
const DRAWERS_COMMON = "src/routes/contracts/drawers/common.tsx";
/** The callers of the drawers' `fieldError` as head 2 left them. No file joins the list. */
const FIELD_ERROR_CALLERS: readonly string[] = ["src/routes/contracts/estimates.tsx"];

function sourceFiles(directory: string = SOURCES): string[] {
  return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) {
      return sourceFiles(path);
    }
    return /\.tsx?$/.test(entry.name) ? [path] : [];
  });
}

/** The source files whose text `pattern` matches, as paths under frontend/. */
function filesWith(pattern: RegExp): string[] {
  return sourceFiles()
    .filter((path) => pattern.test(readFileSync(path, "utf8")))
    .map((path) => relative(FRONTEND, path))
    .sort();
}

describe("DG-FE-06 a refused command is shown by RefusalBanner", () => {
  it("no file under src shows, defines or names ProblemBanner", () => {
    expect(filesWith(/\bProblemBanner\b/)).toEqual([]);
  });

  it("the drawers' fieldError is called where it was left, and nowhere else", () => {
    // The API library has a function of the same name for one error of a problem document; it is
    // not the drawers' and is not counted.
    const callers = filesWith(/(^|[^A-Za-z0-9_.])fieldError\(/m).filter(
      (path) => path !== DRAWERS_COMMON && path !== "src/lib/api/problems.ts",
    );
    expect(callers).toEqual([...FIELD_ERROR_CALLERS]);
  });

  it("the scan reads the tree: it finds the banner that stands in its place", () => {
    expect(filesWith(/<RefusalBanner\b/).length).toBeGreaterThan(40);
  });
});
