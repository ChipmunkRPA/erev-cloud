// The sort keys of the grids on screen (SCREENS §0.5 SCR-URL-09 rev 1.11, SCR-URL-21; DESIGN_SYSTEM
// DS-CMP-10). `sort` is one URL parameter, so on a screen with more than one grid the key of one grid
// reaches the others. Each mounted DataGrid registers the keys its columns list; a grid drops a key it
// does not list only when no other grid on the screen lists it either.

const mounted = new Set<ReadonlySet<string>>();

/** Registers the sort keys of one mounted grid; the returned function removes them on unmount. */
export function registerSortKeys(keys: ReadonlySet<string>): () => void {
  mounted.add(keys);
  return () => {
    mounted.delete(keys);
  };
}

/** Whether a grid other than the one holding `own` lists the key of a `sort` value. */
export function listedByAnotherGrid(sort: string, own: ReadonlySet<string>): boolean {
  const key = sort.startsWith("-") ? sort.slice(1) : sort;
  for (const keys of mounted) {
    if (keys !== own && keys.has(key)) {
      return true;
    }
  }
  return false;
}
