/** Activity log rows (Figma Screen/Admin/ActivityLog 8074:16245). Pure. */

const words = (s: string) => s.replace(/_/g, " ");

/**
 * An Inbox event (action "conversation", notes "conversation <event>") as a verb
 * around its target: "moved MSG-… to Support", "marked MSG-… as resolved".
 */
export function conversationVerb(notes: string | null | undefined): { before: string; after: string } {
  const event = (notes ?? "").replace(/^conversation\s+/, "");
  if (event === "assigned") return { before: "assigned", after: "" };
  if (event === "moved_to_support") return { before: "moved", after: "to Support" };
  if (event.startsWith("status:")) return { before: "marked", after: `as ${words(event.slice(7))}` };
  return { before: event ? `${words(event)}:` : "updated", after: "" };
}

/**
 * "128 actions" for a day. The list is paged, so a day can be cut short: Today
 * (unfiltered) takes the summary's full count; the oldest day shown, when more
 * rows exist, says "50+".
 */
export function dayCount(shown: number, opts: { today?: number | null; cut?: boolean }): string {
  if (opts.today != null && opts.today >= shown) return `${opts.today} action${opts.today === 1 ? "" : "s"}`;
  return `${shown}${opts.cut ? "+" : ""} action${shown === 1 && !opts.cut ? "" : "s"}`;
}
