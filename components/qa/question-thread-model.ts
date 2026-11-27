/**
 * Pure helpers for the question page (Figma Question Detail v6B 7731:15601).
 * Tested in tests/frontend/question-thread-model.test.mjs.
 */

export type Verdict = "yes" | "on_sale" | "other_variant" | "no";

/** The frame's verdict line and the summary's labels, in its order. */
export const VERDICT_LABEL: Record<Verdict, { line: string; summary: string }> = {
  yes: { line: "Yes, get it", summary: "get it" },
  on_sale: { line: "Only on sale", summary: "on sale" },
  other_variant: { line: "Get a different variant", summary: "other variant" },
  no: { line: "No, skip it", summary: "skip it" },
};
export const VERDICT_ORDER: Verdict[] = ["yes", "on_sale", "other_variant", "no"];

/** Verdict Summary: how many answers gave each verdict, and how many gave one. */
export function verdictSummary(answers: { parts?: { verdict?: string | null } | null }[]): {
  counts: Record<Verdict, number>;
  total: number;
} {
  const counts: Record<Verdict, number> = { yes: 0, on_sale: 0, other_variant: 0, no: 0 };
  let total = 0;
  for (const a of answers) {
    const v = a.parts?.verdict as Verdict | undefined | null;
    if (v && v in counts) {
      counts[v] += 1;
      total += 1;
    }
  }
  return { counts, total };
}

/** "Used it 1–6 months · About as expected" -> its lines. */
export function experienceLines(experience: string | null | undefined): string[] {
  return (experience ?? "")
    .split(" · ")
    .map((s) => s.trim())
    .filter(Boolean);
}

/** good / bad are stored "a; b"; older answers may hold one sentence. */
export function pointLines(value: string | null | undefined): string[] {
  return (value ?? "")
    .split(";")
    .map((s) => s.trim())
    .filter(Boolean);
}

/** "Is it for them?": the answer's choice as a tone for its icon. */
export function fitTone(value: string | null | undefined): "yes" | "depends" | "no" {
  const v = (value ?? "").toLowerCase();
  if (v.startsWith("yes")) return "yes";
  if (v.startsWith("no")) return "no";
  return "depends";
}

export type ReplyNode<T> = T & { children: ReplyNode<T>[] };

/** The flat replies (oldest first, each with its parent) as a tree. */
export function replyTree<T extends { id: string; parent_id?: string | null }>(rows: T[]): ReplyNode<T>[] {
  const byId = new Map<string, ReplyNode<T>>();
  for (const r of rows) byId.set(r.id, { ...r, children: [] });
  const roots: ReplyNode<T>[] = [];
  for (const r of rows) {
    const node = byId.get(r.id)!;
    const parent = r.parent_id ? byId.get(r.parent_id) : undefined;
    if (parent) parent.children.push(node);
    else roots.push(node);
  }
  return roots;
}

/** Answers other than the best one, sorted as the "Most helpful" chip says. */
export function sortAnswers<T extends { helpful_votes: number; unhelpful_votes?: number; created_at: string }>(
  answers: T[],
  sort: "helpful" | "newest",
): T[] {
  const copy = [...answers];
  if (sort === "newest") return copy.sort((a, b) => b.created_at.localeCompare(a.created_at));
  return copy.sort(
    (a, b) =>
      b.helpful_votes - (b.unhelpful_votes ?? 0) - (a.helpful_votes - (a.unhelpful_votes ?? 0)) ||
      a.created_at.localeCompare(b.created_at),
  );
}

/**
 * Figma "Screen/Question/Thread" (7735:8020, read 2026-10-05): a thread shows
 * three levels of replies under its root; a reply with more below that depth
 * ends in "Continue this thread · N more replies", which opens the thread view
 * focused on it (`?thread=<reply id>`).
 */
export const THREAD_MAX_DEPTH = 3;

/** Every reply under `node`, at any depth. */
export function descendantCount<T>(node: ReplyNode<T>): number {
  return node.children.reduce((n, c) => n + 1 + descendantCount(c), 0);
}

/**
 * The thread view's data, from the replies already on the page: the focused
 * reply as a tree, and the replies above it (oldest first — "Show N earlier
 * replies"). Null when the id is not a reply of these rows.
 */
export function focusThread<T extends { id: string; parent_id?: string | null }>(
  rows: T[],
  id: string,
): { node: ReplyNode<T>; ancestors: T[] } | null {
  const byId = new Map(rows.map((r) => [r.id, r]));
  if (!byId.has(id)) return null;
  const find = (nodes: ReplyNode<T>[]): ReplyNode<T> | null => {
    for (const n of nodes) {
      if (n.id === id) return n;
      const hit = find(n.children);
      if (hit) return hit;
    }
    return null;
  };
  const node = find(replyTree(rows));
  if (!node) return null;
  const ancestors: T[] = [];
  const seen = new Set<string>([id]);
  let parent = byId.get(id)?.parent_id ? byId.get(byId.get(id)!.parent_id!) : undefined;
  while (parent && !seen.has(parent.id)) {
    seen.add(parent.id);
    ancestors.unshift(parent);
    parent = parent.parent_id ? byId.get(parent.parent_id) : undefined;
  }
  return { node, ancestors };
}
