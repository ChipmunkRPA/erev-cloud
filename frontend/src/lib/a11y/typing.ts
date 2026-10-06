// Single-key shortcuts are off while typing (DESIGN_SYSTEM DS-A11Y-10): a target that takes text input
// keeps J, K, N and E for itself.
export function isTypingTarget(target: EventTarget | null): boolean {
  return (
    target instanceof HTMLElement &&
    (target.isContentEditable || ["INPUT", "SELECT", "TEXTAREA"].includes(target.tagName))
  );
}
