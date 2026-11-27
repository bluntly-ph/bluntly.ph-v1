/** Screen/Seller/Questions (Figma 8196:21469): tabs, cards, Sort / Filter / Search. Pure. */

import type { FilterGroup } from "@/components/console/list-query";

export type StoreQuestion = {
  id: string;
  body: string;
  created_at: string;
  answer_count: number;
  /** Buyers' answers, the store's own left out (Figma "Community answers"). */
  community_answers?: number;
  /** Members following the question (Figma "Following"). */
  followers?: number;
  asker?: { display_name?: string | null; username?: string | null; trust_stage?: number | null } | null;
  store_answer?: { id: string; body: string; created_at: string; edited_at?: string | null } | null;
};

export type QuestionTab = "unanswered" | "answered" | "all";
export const QUESTION_TABS: { key: QuestionTab; label: string }[] = [
  { key: "unanswered", label: "Unanswered" },
  { key: "answered", label: "Answered" },
  { key: "all", label: "All" },
];

export function inQuestionTab(q: StoreQuestion, tab: QuestionTab): boolean {
  return tab === "all" || (tab === "answered") === Boolean(q.store_answer);
}

export function askerOf(q: StoreQuestion): string {
  return q.asker?.display_name || (q.asker?.username ? `@${q.asker.username}` : "A buyer");
}

/** Unanswered count, the oldest one's age, answer rate and median hours to the store's answer. */
export function questionSummary(rows: StoreQuestion[]) {
  const open = rows.filter((q) => !q.store_answer);
  const hours = rows
    .filter((q) => q.store_answer)
    .map((q) => (new Date(q.store_answer!.created_at).getTime() - new Date(q.created_at).getTime()) / 3_600_000)
    .sort((a, b) => a - b);
  const median = hours.length ? (hours.length % 2 ? hours[(hours.length - 1) / 2] : (hours[hours.length / 2 - 1] + hours[hours.length / 2]) / 2) : null;
  const oldest = open.map((q) => new Date(q.created_at).getTime()).sort((a, b) => a - b)[0] ?? null;
  return {
    unanswered: open.length,
    oldest,
    answered: rows.length - open.length,
    total: rows.length,
    rate: rows.length ? (rows.length - open.length) / rows.length : null,
    medianHours: median,
  };
}

/** Menu/Seller/Questions/Sort (Figma 8198:21562). */
export const QUESTION_SORTS: [string, string][] = [
  ["oldest", "Oldest first"],
  ["followed", "Most followed"],
  ["newest", "Newest first"],
];
export const QUESTION_DEFAULT_SORT = "oldest";

const community = (q: StoreQuestion) => q.community_answers ?? q.answer_count;

/**
 * Menu/Seller/Questions/Filter (Figma 8198:21572): Community answers, with
 * counts. The frame's "About: Your store / Products" group is left out: this
 * list holds store questions only. A claimed seller cannot answer a product
 * question (seller_cannot_answer), so a Products option would list rows the
 * store can't act on.
 */
export function questionFilters(rows: StoreQuestion[]): FilterGroup[] {
  const none = rows.filter((q) => community(q) === 0).length;
  return [
    {
      key: "community",
      title: "Community answers",
      options: [
        ["none", "None yet", none],
        ["has", "Has answers", rows.length - none],
      ],
    },
  ];
}

/** Filter, search (question and asker) and sort, as the URL asks. */
export function applyQuestions(rows: StoreQuestion[], q: { sort?: string; community?: string; q?: string }): StoreQuestion[] {
  const words = (q.q ?? "").toLowerCase().split(/\s+/).filter(Boolean);
  const out = rows.filter(
    (x) =>
      (q.community !== "none" || community(x) === 0) &&
      (q.community !== "has" || community(x) > 0) &&
      words.every((w) => `${x.body} ${askerOf(x)}`.toLowerCase().includes(w)),
  );
  const at = (x: StoreQuestion) => new Date(x.created_at).getTime();
  const by =
    q.sort === "newest"
      ? (a: StoreQuestion, b: StoreQuestion) => at(b) - at(a)
      : q.sort === "followed"
        ? (a: StoreQuestion, b: StoreQuestion) => (b.followers ?? 0) - (a.followers ?? 0) || at(a) - at(b)
        : (a: StoreQuestion, b: StoreQuestion) => at(a) - at(b);
  return [...out].sort(by);
}
