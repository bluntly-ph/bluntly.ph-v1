/**
 * Overlay/Store/QuickActions (Figma 8212:23261): what is waiting on the owner,
 * and the frame's four actions (respond to the oldest review, answer the oldest
 * question, link a product, download CSV), behind ⌘K with a search box. Every
 * row goes somewhere real; an action with nothing to act on is left out rather
 * than drawn inert.
 */
export type QuickCounts = { reviews: number; questions: number; appeals: number };

export type QuickIcon = "review" | "question" | "flag" | "pencil" | "link" | "download";

export type QuickAction = {
  key: string;
  group: "Waiting on you" | "Actions";
  label: string;
  icon: QuickIcon;
  /** Extra words the search matches (not shown). */
  words?: string;
  count?: number;
  href?: string;
  /** Opens a dialog in place instead of navigating. */
  opens?: "export";
};

/** The frame's rows, in its order. */
export function quickActions(store: string, counts: QuickCounts): QuickAction[] {
  const base = `/seller/${encodeURIComponent(store)}`;
  const items: QuickAction[] = [
    { key: "reviews", group: "Waiting on you", label: "Reviews that need a response", icon: "review", words: "respond reply", count: counts.reviews, href: `${base}/reviews` },
    { key: "questions", group: "Waiting on you", label: "Unanswered questions", icon: "question", words: "answer", count: counts.questions, href: `${base}/questions` },
    { key: "appeals", group: "Waiting on you", label: "Appeals in progress", icon: "flag", words: "flag fake", count: counts.appeals, href: `${base}/appeals` },
  ];
  if (counts.reviews > 0) {
    items.push({ key: "respond-oldest", group: "Actions", label: "Respond to the oldest review", icon: "pencil", words: "reply waiting", href: `${base}/reviews?respond=oldest` });
  }
  if (counts.questions > 0) {
    items.push({ key: "answer-oldest", group: "Actions", label: "Answer the oldest question", icon: "question", words: "reply waiting", href: `${base}/questions?answer=oldest` });
  }
  items.push(
    { key: "link", group: "Actions", label: "Link a product", icon: "link", words: "products sold catalogue", href: `${base}/products?link=1` },
    { key: "export", group: "Actions", label: "Download CSV", icon: "download", words: "export spreadsheet data", opens: "export" },
  );
  return items;
}

/** Case-insensitive; every typed word has to match the label or its extra words. */
export function filterActions(items: QuickAction[], query: string): QuickAction[] {
  const words = query.toLowerCase().split(/\s+/).filter(Boolean);
  if (words.length === 0) return items;
  return items.filter((i) => {
    const hay = `${i.label} ${i.words ?? ""}`.toLowerCase();
    return words.every((w) => hay.includes(w));
  });
}

/** The oldest row the store still owes something on (`done` says it doesn't). */
export function oldestOpen<T extends { created_at: string }>(rows: T[], done: (row: T) => boolean): T | null {
  let best: T | null = null;
  for (const r of rows) {
    if (done(r)) continue;
    if (!best || new Date(r.created_at).getTime() < new Date(best.created_at).getTime()) best = r;
  }
  return best;
}

/** "Respond to the oldest review": the oldest review without the store's response. */
export function oldestAwaiting<T extends { created_at: string; seller_response?: string | null }>(reviews: T[]): T | null {
  return oldestOpen(reviews, (r) => Boolean(r.seller_response));
}

/** "Answer the oldest question": the oldest question without the store's answer. */
export function oldestUnanswered<T extends { created_at: string; store_answer?: unknown }>(questions: T[]): T | null {
  return oldestOpen(questions, (q) => Boolean(q.store_answer));
}
