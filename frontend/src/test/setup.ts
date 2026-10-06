// Vitest setup, run before every test file (docs/dev-guide.md DG-FE-18; item W-20). One wait for every
// suite: `asyncUtilTimeout` is the time a `findBy…` or `waitFor` assertion may take to become true, not
// what it asserts.
//
// Why five seconds. The first test of a file that renders the app resolves its lazy route module inside
// its first `findBy…`: measured on a busy machine, that test takes 960 to 1,070 ms against Testing
// Library's default of 1,000 ms and 290 to 340 ms with the route module loaded beforehand. So three
// suites (policies/ssp-calculator-run, policies/ssp-book-version, settings/product) failed whenever
// the machine was busy, and a gate that fails on load is ignored. Eight suites had already set the same
// five seconds for themselves.
export {};

// A suite without a DOM waits for nothing on the screen.
if (typeof document !== "undefined") {
  const { configure } = await import("@testing-library/dom");
  configure({ asyncUtilTimeout: 5_000 });
}
