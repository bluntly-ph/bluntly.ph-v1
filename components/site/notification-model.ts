/**
 * The unread badge and where a notification goes (FR-1 1.6).
 *
 * The badge says nothing at zero — a "0" badge is noise that teaches people to
 * ignore it — and caps at "9+" so it keeps its size. A notification's link is
 * already a same-site path from the API; it is checked again here because it
 * becomes an href, and anything else falls back to the notifications page.
 */

export type NotificationItem = {
  id: string;
  kind: string;
  title: string;
  body: string | null;
  link: string | null;
  read_at: string | null;
  /** How many interactions this notice stands for (grouped upvotes). */
  group_count?: number;
  created_at: string;
};

export type NotificationAction = "read" | "unread" | "dismiss";

/**
 * One action applied to the list (QA-064/065): the new list, and how the
 * unread count moves because of it. Pure, so the list, the badge and the
 * tests agree on exactly one answer. An action that changes nothing (reading
 * a read notice, an unknown id) moves the count by 0.
 */
export function applyNotificationAction(
  items: NotificationItem[],
  id: string,
  action: NotificationAction,
  now: string,
): { items: NotificationItem[]; unreadDelta: number } {
  const target = items.find((n) => n.id === id);
  if (!target) return { items, unreadDelta: 0 };
  const wasUnread = !target.read_at;
  if (action === "dismiss") {
    return { items: items.filter((n) => n.id !== id), unreadDelta: wasUnread ? -1 : 0 };
  }
  if (action === "read") {
    if (!wasUnread) return { items, unreadDelta: 0 };
    return { items: items.map((n) => (n.id === id ? { ...n, read_at: now } : n)), unreadDelta: -1 };
  }
  if (wasUnread) return { items, unreadDelta: 0 };
  return { items: items.map((n) => (n.id === id ? { ...n, read_at: null } : n)), unreadDelta: 1 };
}

/** The API call that makes an action durable. */
export function notificationActionRequest(id: string, action: NotificationAction): { path: string; method: string } {
  const base = `/api/bff/api/v1/notifications/${encodeURIComponent(id)}`;
  if (action === "dismiss") return { path: base, method: "DELETE" };
  return { path: `${base}/${action}`, method: "POST" };
}

export function badgeLabel(count: number): string | null {
  if (!(count > 0)) return null;
  return count > 9 ? "9+" : String(Math.floor(count));
}

export function notificationHref(link: string | null | undefined): string {
  if (!link || !link.startsWith("/") || link.startsWith("//") || link.includes("\\")) {
    return "/notifications";
  }
  return link;
}
