import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { CommentThread } from "@/components/review/CommentThread";
import { PricePanel } from "@/components/product/PricePanel";
import { ReportPriceForm } from "@/components/product/ReportPriceForm";
import { ReviewAside } from "@/components/review/ReviewAside";
import { ReviewDetail } from "@/components/review/ReviewDetail";
import { ReviewThreadPanel } from "@/components/review/ReviewThreadPanel";
import { QuickActions } from "@/components/site/QuickActions";
import { SiteFooter } from "@/components/site/SiteFooter";
import { SiteHeader, type HeaderUser } from "@/components/site/SiteHeader";
import { getUser } from "@/lib/dal";
import { getReviewPageData } from "@/lib/reviews";
import { getSessionToken } from "@/lib/session";
import { reviewPhotos } from "@/lib/review-media";
import { shareImageFor } from "@/lib/share-image";

/**
 * QA-070: what a shared review link unfurls as — its title and opening lines,
 * and its picture (the review's photo, else the product's, else the site
 * card). Read WITHOUT the viewer's token, so only what is public can appear:
 * an unpublished review yields the generic, unindexed title and no preview.
 */
export async function generateMetadata({ params }: { params: Promise<{ id: string }> }): Promise<Metadata> {
  const { id } = await params;
  // The anonymous, cached page read: for a signed-out visitor it is the very
  // request the page makes, so Next serves both from one fetch.
  const data = (await getReviewPageData(id).catch(() => null))?.data ?? null;
  if (!data || data.review.published_at == null) {
    return { title: "Review — bluntly", robots: { index: false } };
  }
  const product = data.product?.canonical_name;
  const title = product ? `${product}: ${data.review.title}` : data.review.title;
  const description = shareDescription(data.review.discussion);
  const image = shareImageFor(data.review.photo_url, data.product?.image_url);
  const url = `/reviews/${data.review.id}`;
  return {
    title: `${title} — bluntly`,
    description,
    alternates: { canonical: url },
    openGraph: { type: "article", url, title, description, siteName: "bluntly", images: [{ url: image, alt: title }] },
    twitter: { card: "summary_large_image", title, description, images: [image] },
  };
}

function shareDescription(text: string | null | undefined): string {
  const flat = (text ?? "").replace(/\s+/g, " ").trim();
  if (flat.length <= 180) return flat;
  const cut = flat.slice(0, 180);
  return `${cut.slice(0, Math.max(cut.lastIndexOf(" "), 120)).trimEnd()}…`;
}

export default async function ReviewPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  // The cookie read is local, so the token is free before the network work.
  const token = await getSessionToken();
  // ONE backend call for the whole page (GET /pages/review/{id}, cost plan
  // 2026-10-22), in parallel with the viewer. It replaced seven calls in two
  // rounds: the review, comments and thread, then the price panel, related
  // reviews and payout-removal count, which had to wait for the product id.
  // The token makes the review, thread and comments carry the viewer's own
  // votes (BUG-013); signed out, the read is cached. `getUser` keeps its own
  // catch so a backend wobble degrades to "signed out".
  const [page, me] = await Promise.all([getReviewPageData(id, token), getUser().catch(() => null)]);
  if (!page) notFound();
  const { data, comments, thread, pricePanel, removedAfterPayout } = page;
  // One reading of the clock for every comment's age, so the server's HTML and
  // the client's hydration agree (CommentThread's `ageLabel`). Once per
  // request, in a Server Component: see the seller page for why this is the
  // one place the clock may be read.
  // eslint-disable-next-line react-hooks/purity
  const now = Date.now();

  // The sidebar's related reviews come over-fetched by one, so leaving out the
  // review being read still leaves four.
  const related = page.related.filter((r) => r.id !== id).slice(0, 4);

  const headerUser: HeaderUser = me
    ? { username: me.username, avatarUrl: me.avatar_url, role: me.role }
    : null;

  let canVote = false;
  let isOwnReview = false;
  let voteReadOnly = false;
  let viewerId: string | null = null;
  if (me) {
    viewerId = me.id;
    isOwnReview = me.id === data.author?.id;
    // You may vote on any published review except your own, and never as a
    // claimed seller (Business Rules §9) — both see the counts, not controls.
    voteReadOnly = isOwnReview || Boolean(me.is_claimed_seller);
    canVote = !voteReadOnly;
  }

  return (
    // No SiteHeader here on purpose: the frame gives the review its own orange
    // nav bar carrying back / shop / overflow / search / profile, so the global
    // header would stack a second, redundant one above it.
    <div className="flex min-h-dvh flex-col bg-[var(--surface-app)]">
      {/* Tablet and up get the site's own header; the review's orange bar is
          phone chrome and hides itself at the same breakpoint. The sidebar
          waits for `lg` — 768px has room for navigation, not for a column. */}
      <div className="hidden md:block">
        <SiteHeader user={headerUser} />
      </div>

      <main className="flex-1">
        <div className="mx-auto w-full lg:max-w-[76rem] lg:px-10 lg:py-10">
          <div className="lg:grid lg:grid-cols-[minmax(0,1fr)_20rem] lg:items-start lg:gap-12">
            <div className="min-w-0">
              <ReviewDetail data={data} canVote={canVote} voteReadOnly={voteReadOnly} isOwnReview={isOwnReview} viewer={headerUser} pricePanel={pricePanel} />

              <div className="mx-auto w-full max-w-[44rem] px-4 pb-10 lg:mx-0 lg:max-w-[42rem] lg:px-0">
                {/* FR-2 price panel. Rendered on the review because this is the
                    product surface today — there is no standalone product page.
                    It sits above the comments so price context arrives while the
                    reader is still weighing the verdict, not after the
                    discussion. On desktop it moves into the sidebar, where
                    supporting context belongs. */}
                {thread ? (
                  <ReviewThreadPanel
                    reviewId={id}
                    entries={thread.entries}
                    nextUpdateAt={thread.next_update_at}
                    isOwn={isOwnReview}
                    isRoot={data.review.is_thread_root ?? true}
                    publishedAt={data.review.published_at ?? null}
                    photoReplacedAt={data.review.photo_replaced_at ?? null}
                    photos={reviewPhotos(data.review)}
                  />
                ) : null}
                {removedAfterPayout > 0 ? (
                  <p className="mt-6 text-[12px] leading-[18px] text-[var(--text-secondary)]">
                    {removedAfterPayout === 1
                      ? "1 review of this product was removed by its author after it had earned."
                      : `${removedAfterPayout} reviews of this product were removed by their authors after they had earned.`}
                  </p>
                ) : null}
                {data.product ? (
                  // `price-history` is the target of the "Price History" pill.
                  // Only this phone copy carries it; the desktop sidebar renders
                  // its own panel, and two ids would be invalid.
                  <div id="price-history" className="scroll-mt-24 lg:hidden">
                    <PricePanel panel={pricePanel} />
                    <ReportPriceForm
                      productId={data.product.id}
                      signedIn={Boolean(me)}
                      reviewId={isOwnReview ? id : null}
                    />
                  </div>
                ) : null}
                <CommentThread reviewId={id} initial={comments} viewerId={viewerId} viewerInitial={me?.username?.[0]?.toUpperCase() ?? ""} now={now} />
              </div>
            </div>

            {/* Sticky because the reading column is long — a 2,273px review
                would otherwise strand the product, its price and the Buy action
                at the very top, which is where they are least useful. */}
            <aside className="hidden lg:block lg:sticky lg:top-28">
              <ReviewAside
                data={data}
                panel={pricePanel}
                related={related}
                signedIn={Boolean(me)}
                ownReviewId={isOwnReview ? id : null}
              />
            </aside>
          </div>
        </div>
      </main>
      {/* Screen/Product (7651:5805) draws QuickActions/Button 16px in, 24px up. */}
      <QuickActions />
      <SiteFooter />
    </div>
  );
}
