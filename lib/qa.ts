import "server-only";

import { apiFetch } from "./api/client";
import { questionTag } from "./cache-tags";

export type QAAuthor = {
  id: string;
  username: string | null;
  display_name: string | null;
  trust_stage: number;
  trust_level_name: string | null;
  /** 0..100 (ADR-003); shown beside the level name. See lib/trust.ts. */
  reputation_score: string | null;
  /** The profile photo, when the member has one (no default photo). */
  avatar_url?: string | null;
};

type Schemas = import("@/lib/api-types").components["schemas"];
/** A reply in an answer's thread (0073), as generated from the API. */
export type Reply = Schemas["ReplyOut"];
export type VoteTally = Schemas["VoteTally"];
export type QuestionVote = Schemas["QuestionVoteOut"];

export type Answer = {
  id: string;
  body: string;
  is_best_answer: boolean;
  is_first_responder: boolean;
  /** Written by the store's claimed owner, on a store question. */
  is_seller_answer: boolean;
  /** The store's name, set only on a seller answer. */
  seller_name: string | null;
  helpful_votes: number;
  /** From the vote rows (0073), with the viewer's own vote and the thread. */
  unhelpful_votes?: number;
  my_vote?: "up" | "down" | null;
  replies?: Reply[];
  reply_count?: number;
  created_at: string;
  responder: QAAuthor | null;
  /** The structured parts (experience, good, bad, rating, photos), read from
   *  the body by the API; null for a plain answer. */
  parts?: AnswerParts | null;
  /** Set when the store edited its answer (0081). */
  edited_at?: string | null;
};

export type AnswerParts = {
  text: string;
  experience: string | null;
  good: string | null;
  bad: string | null;
  recommend: boolean | null;
  /** Answer flow step 4: yes / on_sale / other_variant / no. */
  verdict: "yes" | "on_sale" | "other_variant" | "no" | null;
  /** Answer Step 4.1 "Why? (optional)" under the verdict; null when not given. */
  verdict_reason?: string | null;
  right_for_you: string | null;
  rating: string | null;
  photo_urls: string[];
};

export type Question = {
  id: string;
  /** Null for a question asked of a store (0045). */
  product_id: string | null;
  product_name: string | null;
  /** The product's stored image, when there is one (QA-050). */
  product_image_url?: string | null;
  seller_id: string | null;
  seller_name: string | null;
  body: string;
  best_answer_id: string | null;
  answer_count: number;
  created_at: string;
  asker: QAAuthor | null;
  /** The specifics the asker asked for ("Looking for:" line), parsed by the API. */
  requirements?: string[];
};

export type QuestionDetail = Question & {
  answers: Answer[];
  /** QA-058: the Best Answer is the asker's own pick, and says so. */
  best_answer_picked_at?: string | null;
  best_answer_picked_by_asker?: boolean;
  /** QA-045: whether the signed-in viewer asked to be notified. */
  is_subscribed?: boolean;
  /** The question's up-votes and the viewer's own (0073); replies across its answers. */
  upvotes?: number;
  my_upvote?: boolean;
  reply_count?: number;
};

/** Open community questions. Public — no token needed. */
export async function getQuestions(
  productId?: string,
  options: {
    q?: string;
    limit?: number;
    sellerId?: string;
    /** The Questions tab's Time and By-date order (QA-050). */
    period?: "all" | "year" | "month";
    sort?: "newest" | "oldest";
    /** Read past the 60s cache: the admin queue counts what is there now. */
    fresh?: boolean;
  } = {},
): Promise<Question[] | null> {
  try {
    const params = new URLSearchParams({ limit: String(options.limit ?? 30) });
    if (productId) params.set("product_id", productId);
    if (options.sellerId) params.set("seller_id", options.sellerId);
    if (options.period && options.period !== "all") params.set("period", options.period);
    if (options.sort === "oldest") params.set("sort", "oldest");
    // Free text, for the Questions tab on /search. The API matches the question
    // wording and the product name; a blank string is not a query, so it is
    // omitted rather than sent as an empty filter.
    const needle = options.q?.trim();
    if (needle) params.set("q", needle);
    return await apiFetch<Question[]>(`/api/v1/questions?${params}`, options.fresh ? {} : {
      revalidate: 60,
    });
  } catch {
    // See lib/requests.ts: null distinguishes "unreachable" from "none".
    return null;
  }
}

/**
 * One question with its answers.
 *
 * QA-044: an answer posted a moment ago must be on the page the router
 * refreshes to. A signed-in read carries the token, which apiFetch never
 * caches (and which also brings the viewer's own "Notify me" state); a
 * signed-out read is cached under `question:<id>`, which the BFF expires on
 * every write to that question (lib/cache-tags.ts).
 */
export async function getQuestionDetail(
  id: string,
  token?: string | null,
): Promise<QuestionDetail | null> {
  try {
    return await apiFetch<QuestionDetail>(`/api/v1/questions/${id}`, {
      token,
      ...(token ? {} : { revalidate: 60, tags: [questionTag(id)] }),
    });
  } catch {
    return null;
  }
}
