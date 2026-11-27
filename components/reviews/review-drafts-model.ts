/**
 * Where an unfinished review lives, and how two copies of it are reconciled
 * (QA-003).
 *
 * The composer kept drafts only in this browser's localStorage, so a review
 * begun on a laptop never appeared on the reviewer's phone. Drafts now live with
 * the account (GET/PUT/DELETE /api/v1/review-drafts); localStorage stays as the
 * instant, offline copy. When both hold a slot, the newer save wins — the same
 * rule the API applies — so neither device can roll the other back.
 *
 * The local key is per account. The old key was shared by everyone who signed
 * in on the device, so on a shared computer the next person was offered the
 * previous person's unfinished reviews.
 */

/** Per-account local key. */
export function localDraftsKey(userId: string): string {
  return `bluntly:review-drafts:v3:${userId}`;
}

/** The pre-account key. Adopted once by whoever opens the composer next, then dropped. */
export const UNSCOPED_DRAFTS_KEY = "bluntly:review-drafts:v2";

/** The composer keeps ten; so does the account. */
export const MAX_DRAFTS = 10;

export type StoredDraft = { savedAt?: number } & Record<string, unknown>;
export type ServerDraft = { slot: string; draft: StoredDraft; saved_at: number };

/**
 * Local and server copies, one per slot, the newer save of each; newest first,
 * at most MAX_DRAFTS. Pure, so the rule is testable without a browser.
 */
export function mergeDrafts(
  local: Record<string, StoredDraft>,
  server: readonly ServerDraft[],
): { slot: string; draft: StoredDraft }[] {
  const best = new Map<string, StoredDraft>();
  for (const [slot, draft] of Object.entries(local)) best.set(slot, draft);
  for (const entry of server) {
    const mine = best.get(entry.slot);
    const theirs = { ...entry.draft, savedAt: entry.saved_at };
    if (!mine || (mine.savedAt ?? 0) < entry.saved_at) best.set(entry.slot, theirs);
  }
  return [...best.entries()]
    .map(([slot, draft]) => ({ slot, draft }))
    .sort((a, b) => (b.draft.savedAt ?? 0) - (a.draft.savedAt ?? 0))
    .slice(0, MAX_DRAFTS);
}

/** The BFF path for one slot. Slots are product ids or a fixed marker; encoded anyway. */
export function draftUrl(slot?: string): string {
  const base = "/api/bff/api/v1/review-drafts";
  return slot === undefined ? base : `${base}/${encodeURIComponent(slot)}`;
}
