// Live announcements (DESIGN_SYSTEM DS-A11Y-08; docs/dev-guide.md DG-FE-10). The shell mounts one
// polite region (`role="status"`) and one assertive region (`role="alert"`); everything else speaks
// only through announce(). An identical message within 1 second is dropped.
export type Politeness = "polite" | "assertive";

export const DUPLICATE_WINDOW_MS = 1_000;

type Speak = (message: string) => void;

const regions: Record<Politeness, Speak | null> = { polite: null, assertive: null };
let last: { readonly message: string; readonly at: number } | null = null;

/** Registers the shell's live regions; the returned function unregisters them. */
export function registerLiveRegions(polite: Speak, assertive: Speak): () => void {
  regions.polite = polite;
  regions.assertive = assertive;
  return () => {
    if (regions.polite === polite) {
      regions.polite = null;
      regions.assertive = null;
    }
  };
}

export function announce(message: string, politeness: Politeness = "polite"): void {
  const now = Date.now();
  if (last !== null && last.message === message && now - last.at < DUPLICATE_WINDOW_MS) {
    return;
  }
  last = { message, at: now };
  regions[politeness]?.(message);
}
