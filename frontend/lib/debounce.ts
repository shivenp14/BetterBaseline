/** Schedule one trailing callback; callers cancel the previous schedule on edits. */
export function scheduleDebounced(callback: () => void, delayMs: number): () => void {
  const timer = window.setTimeout(callback, delayMs);
  return () => window.clearTimeout(timer);
}
