import type { Metadata } from "next";

import { ReviewQueueScreen } from "@/components/admin/ReviewQueueScreen";
import { allReviewsApiQuery, parseAllReviewsFilters } from "@/components/admin/all-reviews-model";
import {
  isTab,
  parseQueueFilters,
  queueApiQuery,
  reportsApiQuery,
  type Tab,
} from "@/components/admin/review-queue-model";
import { getAllReviews, getQueue, getReports, type QueueItem } from "@/lib/moderation";
import { getAdminSellerAppeals } from "@/lib/sellers";
import { getUser } from "@/lib/dal";
import { getQuestions } from "@/lib/qa";
import { getAdminSupportRequests } from "@/lib/support";

export const metadata: Metadata = {
  title: "Review queue — bluntly admin",
};

/**
 * The Review Queue's own route.
 *
 * The URL carries the whole question: which tab, and which slice of the
 * backlog. `tab` lets the Overview's Queue Breakdown and the header's overdue
 * badge link straight to a filtered queue, and lets an administrator share the view
 * they are looking at.
 *
 * The queue itself is filtered, ordered and paginated SERVER-side against the
 * whole backlog (`referral_service.get_prioritized_queue`). This page validates
 * the URL against the policy's own vocabulary and forwards nothing else — a
 * hand-edited `?band=critical` narrows to "no band filter" rather than putting
 * a 422 on an administrator's screen.
 *
 * The screen is built to 6922:837 "Admin Page - Review Queue", the 1280x1943
 * frame that replaced the deleted 5017:x set on 2026-09-09 — see
 * `ReviewQueueScreen` for the column-by-column reading and for the cells the
 * frame draws that this build has no source for.
 */
export default async function ReviewQueuePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const first = (value: string | string[] | undefined) =>
    Array.isArray(value) ? (value[0] ?? "") : (value ?? "");

  const search = new URLSearchParams();
  for (const key of ["band", "lane", "sla", "factor", "q", "tier", "sort", "rsort", "rstatus", "rpage", "view", "limit", "offset"]) {
    const value = first(params[key]);
    if (value) search.set(key, value);
  }
  const filters = parseQueueFilters(search);

  const rawTab = first(params.tab);
  const tab: Tab = isTab(rawTab) ? rawTab : "reviews";

  // All Reviews reads its own prefixed parameters (`aq`, `astate`…) and is
  // fetched only when its tab is open: every other tab pays nothing for it.
  const allSearch = new URLSearchParams();
  for (const key of ["aq", "astate", "aearn", "afrom", "ato", "asort", "aoffset"]) {
    const value = first(params[key]);
    if (value) allSearch.set(key, value);
  }
  const allFilters = parseAllReviewsFilters(allSearch);

  // The Answers tab reads the public Q&A endpoints. There is no `/admin` Q&A
  // route and this needs none: `GET /questions` already returns the asker,
  // the answer count and the trust of everyone involved, and the per-question
  // detail is fetched through the BFF only for the row an administrator opens.
  // `getQuestions` returns null when the API is unreachable — a failing Q&A
  // list must not blank the review queue, same defence as `getReports`. That
  // null is passed THROUGH rather than flattened to []: an outage and an empty
  // queue are different facts, and the tab says which one it is. `getQueue`
  // now answers the same way, with a discriminated result.
  // Seller support requests (owner decision 2026-09-28): `null` on an outage,
  // like the Q&A list, so the tab can tell an outage from an empty queue.
  const [queue, reportsPage, questions, support, allReviews, sellerFlags, me] = await Promise.all([
    getQueue(queueApiQuery(filters)),
    getReports(reportsApiQuery(filters)),
    // Uncached and up to 100 threads: the tab's count is the list it shows,
    // read now — the public 60s cache made it differ between renders.
    getQuestions(undefined, { limit: 100, fresh: true }),
    getAdminSupportRequests(),
    tab === "all" ? getAllReviews(allReviewsApiQuery(allFilters)) : Promise.resolve(null),
    // MQA-040: stores' flags on reviews of their own store are decided in Sellers ›
    // Appeals; the Reports view says how many wait there, so none goes unseen.
    getAdminSellerAppeals(),
    getUser(),
  ]);

  // `?open=<review id>` (the Overview's queue card links here): the modal opens
  // on that review. When it is not on this page, look it up across the whole
  // queue, in the same policy order, rather than opening nothing.
  const open = first(params.open);
  let openItem: QueueItem | null = null;
  if (open && queue.available && !queue.items.some((i) => i.review.id === open)) {
    // Either view: a link to a taken-down review (MQA-015) still opens it.
    for (const view of ["waiting", "taken_down"]) {
      const wide = await getQueue(`limit=100&view=${view}`);
      openItem = wide.available ? (wide.items.find((i) => i.review.id === open) ?? null) : null;
      if (openItem) break;
    }
  }

  return (
    <ReviewQueueScreen
      openItem={openItem}
      queue={queue}
      filters={filters}
      reports={reportsPage.items}
      reportTotals={{ reports: reportsPage.total, items: reportsPage.itemsTotal }}
      questions={questions}
      support={support}
      initialTab={tab}
      now={queue.fetchedAt}
      allReviews={allReviews}
      allFilters={allFilters}
      sellerFlags={sellerFlags?.length ?? null}
      superAdmin={me?.role === "super_admin"}
    />
  );
}
