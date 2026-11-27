/**
 * MQA-032: an icon's unread count as its badge reads - nothing at zero, the
 * number up to 9, then "9+". One unread reply and ten no longer look alike.
 */
export function unreadBadge(count: number): string | null {
  if (!Number.isFinite(count) || count <= 0) return null;
  return count > 9 ? "9+" : String(Math.floor(count));
}
