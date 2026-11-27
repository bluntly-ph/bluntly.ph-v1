/**
 * The comment thread's shape rules, testable without a browser (QA-029/039).
 *
 * Threads are two levels (Business Rules §8 conversation; the API refuses a
 * reply to a reply). Two rules follow:
 *
 * * Deleting. A deleted comment is gone from the thread — the retest saw a
 *   "[removed]" row stay after confirming and read it as a failed delete. The
 *   one exception is a top comment that still has live replies: it stays as a
 *   tombstone so the replies keep their context. When its last reply goes, the
 *   tombstone goes too. The API lists threads by the same rule, so a refresh
 *   cannot bring a deleted comment back.
 * * Replying to a reply. It joins the same thread (the top comment's), opened
 *   with the person being answered, so every comment can be answered without
 *   a third level the API does not have.
 */

type Node = {
  id: string;
  is_removed?: boolean;
  replies: Node[];
};

/** The thread as it should be shown: removed replies dropped, empty tombstones dropped. */
export function visibleThread<T extends Node>(list: T[]): T[] {
  return list.flatMap((c) => {
    const replies = c.replies.filter((r) => !r.is_removed) as T["replies"];
    if (c.is_removed && replies.length === 0) return [];
    return [{ ...c, replies }];
  });
}

/** Mark `id` removed wherever it is, then apply the visibility rule. */
export function removeFromThread<T extends Node>(list: T[], id: string): T[] {
  const marked = list.map((c) =>
    c.id === id
      ? { ...c, is_removed: true }
      : { ...c, replies: c.replies.map((r) => (r.id === id ? { ...r, is_removed: true } : r)) },
  );
  return visibleThread(marked);
}

/** How a reply to a reply opens: addressed to that person, in plain text. */
export function replyOpening(handle: string | null | undefined): string {
  const clean = (handle ?? "").replace(/[^A-Za-z0-9_.-]/g, "");
  return clean ? `@${clean} ` : "";
}
