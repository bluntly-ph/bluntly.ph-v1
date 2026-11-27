import "server-only";

import { apiFetch } from "./api/client";
import { reviewTag } from "./cache-tags";

/**
 * Read side for the review comment thread (BUG-014).
 *
 * Fetched server-side so the thread is in the first HTML payload rather than
 * appearing a beat after hydration. Mutations go the other way — through the BFF
 * from the client component, so the session token stays on the server.
 */

export type CommentAuthor = {
  id: string;
  username: string | null;
  display_name: string | null;
  avatar_url: string | null;
  trust_stage: number | null;
  trust_level_name: string | null;
  /** The public 0-100 score the Honesty Score badge draws (§17: public on every profile). */
  reputation_score?: string | number | null;
  /** Business Rules §8/§9: a claimed seller joining the conversation. */
  is_claimed_seller?: boolean;
  /** §8: the visible "new account" badge (under 30 days old). */
  is_new_account?: boolean;
};

export type Comment = {
  id: string;
  review_id: string;
  parent_id: string | null;
  body: string;
  helpful_votes: number;
  unhelpful_votes: number;
  is_removed: boolean;
  created_at: string;
  author: CommentAuthor | null;
  my_vote: "up" | "down" | null;
  replies: Comment[];
  /** §8: heavily downvoted comments auto-collapse for everyone. */
  is_collapsed?: boolean;
  /** QA-069: the viewer's own follow / save; never anyone else's. */
  followed_by_me?: boolean;
  saved_by_me?: boolean;
};

/**
 * The thread for a review, oldest first, replies nested one level.
 *
 * A failure returns an empty thread rather than throwing: a comments outage
 * should cost the reader the discussion, not the review they came to read.
 */
export async function getComments(
  reviewId: string,
  token?: string | null,
): Promise<Comment[]> {
  try {
    return await apiFetch<Comment[]>(`/api/v1/reviews/${reviewId}/comments`, {
      token,
      // Only takes effect for signed-out readers: apiFetch drops `revalidate`
      // whenever a token is present, so a signed-in thread — which carries that
      // viewer's own `my_vote` — is never shared. Signed-out responses have
      // `my_vote: null` throughout and are identical for everyone.
      revalidate: 30,
      tags: [reviewTag(reviewId)],
    });
  } catch {
    return [];
  }
}

/** The parent review of a comment, as a profile row draws it. */
export type CommentReview = {
  id: string;
  title: string;
  product_name: string | null;
  helpful_votes: number;
  comment_count: number;
};

/** One comment a member wrote, for the profile's Comments tab. */
export type AuthoredComment = {
  id: string;
  body: string;
  helpful_votes: number;
  created_at: string;
  review: CommentReview;
};

/**
 * Everything a member has said, newest first (profile Comments tab).
 *
 * `null` on failure rather than `[]`, matching `searchReviews`: an outage and
 * an empty history are different answers and the tab says so differently. The
 * API already filters removed comments and unpublished reviews out — a profile
 * is a public page, so nothing here depends on who is reading.
 */
export async function getAuthoredComments(
  userId: string,
  limit = 24,
): Promise<AuthoredComment[] | null> {
  try {
    return await apiFetch<AuthoredComment[]>(
      `/api/v1/users/${userId}/comments?limit=${limit}`,
      { revalidate: 60 },
    );
  } catch {
    return null;
  }
}

/** One comment the signed-in member saved (QA-069). */
export type SavedComment = {
  id: string;
  body: string;
  created_at: string;
  author: CommentAuthor | null;
  review: CommentReview;
};

/**
 * The signed-in member's saved comments, most recently saved first. Private:
 * the API reads the member from the session, never from the URL, and this is
 * never cached (the token disables `revalidate` in apiFetch). `null` on
 * failure, as for the other lists.
 */
export async function getSavedComments(token: string | null, limit = 50): Promise<SavedComment[] | null> {
  if (!token) return null;
  try {
    return await apiFetch<SavedComment[]>(`/api/v1/users/me/saved-comments?limit=${limit}`, { token });
  } catch {
    return null;
  }
}
