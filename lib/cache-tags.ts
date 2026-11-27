/**
 * Cache tags for the public review read models, and which writes expire them.
 *
 * Public review reads are kept in Next's Data Cache for 60 seconds (signed-out
 * reads only — lib/api/client.ts never caches a credentialed response). Nothing
 * expired them after a write, so on 2026-09-18 an upvote committed at once and
 * the API returned the new count, while the review page and every card that
 * showed it kept serving the old count for a minute and one more request
 * (production probe: 0 -> vote -> still 0 at +65 s -> 1 on the next request).
 *
 * Two tags, because a write to one review changes two kinds of read:
 *
 *   review:<id>   that review's own reads: its detail and its comments
 *   review-lists  every list a review card can appear in — feed, search,
 *                 landing, categories, public profiles — since a card carries
 *                 the review's counts and any list may hold it
 *
 * The BFF (app/api/bff/[...path]/route.ts) expires them after a successful
 * write, so a mutation invalidates only the review read models, and caching
 * stays on for everything else.
 *
 * Votes, comments and reports expire the review's own reads but NOT the lists
 * (2026-10-22). They change a card's counts, never which reviews a list holds,
 * and expiring every list on every vote meant the 60-second list cache almost
 * never survived: each miss is a render's worth of backend calls and database
 * reads. A list may show a count up to a minute old; the review page itself is
 * still exact. Writes that change what a list holds or what a card says
 * (create, edit, a new entry, delete, an administrator's decision on the
 * review or on a report) still expire the lists.
 */

export const REVIEW_LISTS = "review-lists";

export function reviewTag(id: string): string {
  return `review:${id}`;
}

/** A question's own cached read (QA-044): its detail and answers. */
export function questionTag(id: string): string {
  return `question:${id}`;
}

const UUID = "[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}";

/** A write to one review: vote, comment, edit, report, or an administrator decision. */
const REVIEW_WRITE = new RegExp(`^api/v1/(?:admin/)?reviews/(${UUID})(?:/|$)`);

/** Writes that change only the review's own counts, never a list's contents. */
const COUNTS_ONLY = new RegExp(`^api/v1/reviews/${UUID}/(?:vote|comments|report|critique)$`);

/** A new review: public from submission (Business Rules §2), so it joins lists. */
const REVIEW_CREATE = /^api\/v1\/reviews$/;

/** Any write under one question: an answer, a Best Answer pick, "Notify me". */
const QUESTION_WRITE = new RegExp(`^api/v1/questions/(${UUID})(?:/|$)`);

/** An administrator's report decision, which can take a review down. */
const REPORT_DECISION = new RegExp(`^api/v1/admin/reports/${UUID}/decision$`);

/**
 * The tags to expire after a successful BFF request, or none.
 *
 * `path` is the BFF path without a leading slash (`api/v1/reviews/<id>/vote`).
 * Reads never expire anything. A report decision names its review only in the
 * response body, so the caller passes that id as `reportedReviewId`.
 */
export function tagsToExpire(
  method: string,
  path: string,
  reportedReviewId?: string | null,
): string[] {
  if (method === "GET" || method === "HEAD") return [];
  if (REVIEW_CREATE.test(path)) return method === "POST" ? [REVIEW_LISTS] : [];
  const review = REVIEW_WRITE.exec(path);
  if (review) {
    const tag = reviewTag(review[1].toLowerCase());
    return COUNTS_ONLY.test(path) ? [tag] : [tag, REVIEW_LISTS];
  }
  const question = QUESTION_WRITE.exec(path);
  if (question) return [questionTag(question[1].toLowerCase())];
  if (REPORT_DECISION.test(path)) {
    return reportedReviewId ? [reviewTag(reportedReviewId.toLowerCase()), REVIEW_LISTS] : [REVIEW_LISTS];
  }
  return [];
}

/** True for a path whose response must be read to find the review it touched. */
export function isReportDecision(path: string): boolean {
  return REPORT_DECISION.test(path);
}
