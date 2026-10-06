// The search of a panel-tab change (SCREENS SCR-URL-13, SCR-URL-20; DESIGN_SYSTEM DS-CMP-07; crawl finding
// F4). On a screen whose panes hold their own lists, `sort`, `q`, `view` and the `f.*` chips belong to the
// pane that wrote them. A tab change takes them out of the URL with the `pane` it leaves: the next pane's
// grid would read a key it does not list as an unrecognised link value and say so (SCR-URL-21), about a
// link nobody followed. A screen whose list stays mounted across its panes (the obligations list beside
// the obligation pane) keeps its parameters and does not use this helper.
export const PANE_PARAM = "pane";

/**
 * SCR-URL-07 to SCR-URL-10: `sort` of the DataGrid, `q` and the `f.` prefix of the FilterBar, `view` of
 * the saved-view selector. Written out so that a screen module does not load those components for
 * their names; `pane-params.test.ts` holds the two lists together.
 */
export const LIST_PARAMS: ReadonlySet<string> = new Set(["sort", "q", "view"]);
export const LIST_PARAM_PREFIX = "f.";

/** `current` with `pane` set, or removed for the default tab (null), and without the list parameters. */
export function withPane(current: URLSearchParams, pane: string | null): URLSearchParams {
  const next = new URLSearchParams(current);
  for (const name of [...next.keys()]) {
    if (LIST_PARAMS.has(name) || name.startsWith(LIST_PARAM_PREFIX)) {
      next.delete(name);
    }
  }
  if (pane === null) {
    next.delete(PANE_PARAM);
  } else {
    next.set(PANE_PARAM, pane);
  }
  return next;
}
