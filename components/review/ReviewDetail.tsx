import Image from "next/image";
import Link from "next/link";
import {
  ArrowLeft,
  ArrowSquareOut,
  ChartLine,
  ChatCenteredText,
  Chats,
  Check,
  DotOutline,
  Info,
  SealCheck,
  ShoppingBagOpen,
  UserCircle,
  X,
} from "@phosphor-icons/react/dist/ssr";

import { BackControl } from "@/components/site/BackControl";
import { AuthorHeader } from "@/components/review/AuthorHeader";

import { ReadingTelemetry } from "@/components/review/ReadingTelemetry";
import { disclosureLabel } from "@/components/reviews/disclosure-model";
import { LISTING_NOTE, listingLink } from "@/components/review/listing-link-model";
import { ReportDialog } from "@/components/review/ReportDialog";
import { ReviewOverflowMenu } from "@/components/review/ReviewOverflowMenu";
import { ReviewVoteBar } from "@/components/review/ReviewVoteBar";
import { ShareButton } from "@/components/review/ShareButton";
import { PriceHistorySheet } from "@/components/product/PriceHistorySheet";
import type { PricePanel } from "@/lib/products";
import type { HeaderUser } from "@/components/site/SiteHeader";
import { StarRow } from "@/components/sellers/SellerIdentity";
import { peso } from "@/lib/products";
import { ageLabel, usablePhoto, type ReviewFull, type Verdict } from "@/lib/reviews";
import { reviewPhotos } from "@/lib/review-media";
import { ReviewPhotoCarousel } from "@/components/review/ReviewPhotoCarousel";
import { shareImageFor } from "@/lib/share-image";
import { trustScore } from "@/lib/trust";
import { isStaffRole } from "@/lib/roles";

/**
 * A published review, built to Figma "Screen/Product" (7651:5805, re-read
 * 2026-10-05; it replaced "Review page" 4218:1196): the orange bar on phones;
 * the ProductPanel (product thumbnail and name, Price history and Ask a
 * question tools); then the review as one white card at radius 24 — Author
 * (shared AuthorHeader: stage and Honesty Score), the title in 20px Medium over
 * RatingMeta (stars and the verdict preset), the Gallery, and the sections with
 * 12px trust-blue labels: Verdict (the reviewer's words), Pros & Cons
 * (Attribute circles), Experience, Best for, This is not for, General info —
 * then the ActionBar (vote, comments, Shop, Share).
 *
 * INTENTIONAL PRODUCT DIFFERENCES:
 *  - "General Info" and "Experience" are one field here (`discussion`), under
 *    "Experience"; "General info" carries the price paid when there is one.
 *    "Best for" is kept because the composer collects it.
 *  - Verification (X.2) and disclosure (X.1) sit under the gallery: both
 *    qualify everything below them.
 *  - "3D model" is not drawn: no product carries 3D or 360 assets (X.3).
 *  - Pros and cons carry no aspect ("Price", "Portability"), so each point is
 *    its label alone.
 *  - NO PHOTO = NO DEFAULT PHOTO: the gallery is the review's own uploads only;
 *    the product's image appears in the ProductPanel, as product context.
 *  - From `md` up there is no frame: the page renders SiteHeader instead of the
 *    orange bar, and the desktop sidebar keeps the product card.
 */

/** The structured verdict's own label (QA-066): a chip, not a sentence. */
const VERDICT_PRESET: Record<Verdict, string> = {
  yes_absolutely: "Yes, absolutely",
  it_depends: "It depends",
  hard_pass: "Hard pass",
};


const BAR_BUTTON = "grid h-10 w-10 place-items-center rounded-full hover:bg-white/15";

const Dot = ({ className = "" }: { className?: string }) => (
  <DotOutline size={12} aria-hidden="true" className={`shrink-0 text-[var(--base-gray-400)] ${className}`} />
);

function compact(n: number): string {
  if (n < 1000) return String(n);
  if (n < 1_000_000) return `${(n / 1000).toFixed(1).replace(/\.0$/, "")}k`;
  return `${(n / 1_000_000).toFixed(1).replace(/\.0$/, "")}m`;
}

/**
 * The reviewer's photo on the frame's #e1e1e1 media ground, cropped to fill as
 * drawn. The hero is this page's LCP element, so it is the one image that loads
 * eagerly.
 *
 * QA-060: one proportion at every width. It was square on phones, 16:10 from
 * `md`, and at `lg` a height cap overrode the ratio again — three different
 * crops of the same photo. Square is the mobile frame's, and the shape
 * marketplace product photos already have; on wide screens it is capped and
 * centred rather than stretched.
 *
 * Only the review's own uploaded photo is drawn here. The product's listing
 * image used to stand in when there was none (QA-060), which presented it as
 * the reviewer's evidence (owner bug report, 2026-10-03). Without a photo the
 * review shows no media area at all; the product's image stays in the
 * ProductPanel and the sidebar, where it is about the product.
 */
function ReviewHero({ review }: { review: ReviewFull["review"] }) {
  const photos = reviewPhotos(review);
  // NO PHOTO = NO DEFAULT PHOTO (owner, 2026-10-05): with no upload there is
  // no media area at all — the Gallery is left out, as ReviewQuoteCard's
  // Photos=No does — rather than a placeholder box where a photo would be.
  if (photos.length === 0) return null;
  if (photos.length > 1) {
    return (
      <div className="mx-auto w-full max-w-[28rem]">
        <ReviewPhotoCarousel photos={photos} alt={review.title} />
      </div>
    );
  }
  return (
    <div className="relative mx-auto aspect-square w-full max-w-[28rem] overflow-hidden rounded-[12px] bg-[#e1e1e1]">
      <Image
        src={photos[0]}
        alt={review.title}
        fill
        sizes="(min-width: 480px) 28rem, 100vw"
        priority
        className="object-cover"
      />
    </div>
  );
}

export function ReviewDetail({
  data,
  canVote,
  voteReadOnly = false,
  isOwnReview = false,
  viewer = null,
  pricePanel = null,
}: {
  data: ReviewFull;
  /** GET /products/{id}/prices, as the page read it, for the Price history sheet. */
  pricePanel?: PricePanel | null;
  canVote: boolean;
  /** Own review or a claimed seller: counts, not vote controls. */
  voteReadOnly?: boolean;
  /** The author can't report their own review — the API rejects self-reports. */
  isOwnReview?: boolean;
  /** The signed-in reader, for the bar's avatar. */
  viewer?: HeaderUser;
}) {
  const { review, author, product } = data;
  const listing = listingLink(data.listing_url, data.listing_platform);
  const authorName = author?.display_name || author?.username || "reviewer";
  // The console role of the current architecture. It only decides whether the
  // takedown is OFFERED; the API refuses anyone else.
  const isStaffViewer = isStaffRole(viewer?.role);
  const authorAvatar = usablePhoto(author?.avatar_url);
  const viewerAvatar = usablePhoto(viewer?.avatarUrl);
  const hasScore = trustScore(author?.reputation_score) !== null;
  const hasPros = (review.pros?.length ?? 0) > 0;
  const hasCons = (review.cons?.length ?? 0) > 0;
  // §3: "Photo provided" — what was checked, never a purchase claim.
  const verified = Boolean(review.photo_provided);
  const disclosure = disclosureLabel(review.material_relationship);
  const commentCount = data.comment_count ?? 0;

  return (
    <>
      {/* Renders nothing. One per review detail, keyed implicitly by the prop
          it takes — a new review.id on this same route re-runs its whole
          lifecycle as a fresh impression. */}
      <ReadingTelemetry reviewId={review.id} />

      {/* Phone chrome only: it replaces the site header rather than stacking
          under it, and sticks through a long read. The #d9d9d9 strip above it in
          the frame is the phone status bar, device chrome, so it is not built.
          Hidden from `md` up, where the page renders SiteHeader instead. */}
      <nav
        aria-label="Review"
        className="sticky top-0 z-30 flex h-[72px] items-center justify-between bg-[var(--accent-primary)] px-4 text-[var(--text-on-brand)] md:hidden"
      >
        {/* BUG-033: this was a Link to "/", so a reader who came from Search
            lost their results and their place. It goes back now, and only
            falls back to Home for a review opened directly in a fresh tab. */}
        <BackControl fallbackHref="/" className={`-ml-1.5 ${BAR_BUTTON}`}>
          <ArrowLeft size={28} />
        </BackControl>

        <div className="flex items-center gap-2">
          {review.referral_redirect_url ? (
            <a
              href={review.referral_redirect_url}
              target="_blank"
              rel="nofollow sponsored noopener noreferrer"
              aria-label="Buy this product"
              data-telemetry-outlink
              data-telemetry-review-id={review.id}
              className={BAR_BUTTON}
            >
              <ShoppingBagOpen size={28} />
            </a>
          ) : null}
          <ReviewOverflowMenu title={review.title} reviewId={review.id} canReport={!isOwnReview} canDelete={isOwnReview} isRoot={review.is_thread_root ?? true} canTakeDown={isStaffViewer && !isOwnReview && review.published_at != null} onBar />
          {/* The 40px avatar ends on the 16px gutter, 14px past the overflow. */}
          <Link
            href="/profile"
            aria-label="Your profile"
            className="ml-1.5 grid h-10 w-10 place-items-center overflow-hidden rounded-full hover:opacity-90"
          >
            {viewerAvatar ? (
              <Image
                src={viewerAvatar}
                alt=""
                width={40}
                height={40}
                className="h-10 w-10 rounded-full object-cover"
              />
            ) : (
              <UserCircle size={40} weight="light" />
            )}
          </Link>
        </div>
      </nav>

      <article className="mx-auto w-full max-w-[44rem] px-2 pb-6 pt-4 md:px-4 md:py-6 lg:mx-0 lg:max-w-[42rem] lg:px-0 lg:py-0">
        {/* Figma "ProductPanel" (7660:5862 in Screen/Product 7651:5805, read
            2026-10-05): "Product link at the top of review and question detail
            pages, with price history, 3D model and ask shortcuts." White at
            radius 16, 12px in; a 40px product thumbnail (product context — never
            the review's media) and the name in 12px; the ProductTool tiles on
            #f2f2f2 at radius 12, a 20px glyph over a 12px label. The 3D model
            tile is not drawn: no product carries a 3D model (owner rule). */}
        <ProductPanel
          product={product}
          tools={
            <>
              {product ? (
                <PriceHistorySheet
                  productId={product.id}
                  productName={product.canonical_name}
                  initial={pricePanel}
                  listing={listing ? { href: listing.href, platform: data.listing_platform ?? null } : null}
                  reportHref="#price-history"
                  triggerClassName={TOOL}
                  triggerContent={
                    <>
                      <ChartLine size={20} aria-hidden="true" />
                      Price history
                    </>
                  }
                />
              ) : null}
              <Link href="/questions/new" className={TOOL}>
                <ChatCenteredText size={20} aria-hidden="true" />
                Ask a question
              </Link>
            </>
          }
        />

        {/* Figma "Review/Card" (7651:5839): white at radius 24, 20px top, 16px
            sides, 24px bottom; the Author header, the lead (title and rating),
            the gallery, then the sections 20px apart and the ActionBar. */}
        <div className="mt-4 rounded-[24px] bg-[var(--surface-card)] px-4 pb-6 pt-5 md:px-6">
        <AuthorHeader
          name={author?.username ?? authorName}
          href={author?.id ? `/u/${author.id}` : null}
          avatarUrl={authorAvatar}
          age={ageLabel(review.created_at)}
          levelName={author?.trust_level_name}
          stage={author?.trust_stage}
          score={author && hasScore ? author.reputation_score : null}
          trailing={
            // The phone keeps these in its orange bar (`md:hidden`). From `md`
            // they are the author line's own right end — copy the link, report
            // the review — as plain buttons, not a menu over the headline
            // (QA-059).
            <span className="hidden md:block">
              <ReviewOverflowMenu title={review.title} reviewId={review.id} canReport={!isOwnReview} canDelete={isOwnReview} isRoot={review.is_thread_root ?? true} canTakeDown={isStaffViewer && !isOwnReview && review.published_at != null} inline />
            </span>
          }
        />

        {/* "Lead": the reviewer's title in 20px Medium on a 28px line, 8px over
            RatingMeta ("Stars • verdict line", 7659:6243) — the 20px stars 4px
            apart, then the structured verdict (QA-066: a label of its own, not
            the start of the reviewer's sentence). The product is named in the
            ProductPanel above, so the title is the reviewer's words alone. */}
        <h1 className="mt-5 break-words text-[20px] font-medium leading-7 text-[var(--text-primary)] [overflow-wrap:anywhere]">
          {review.title}
        </h1>
        <p className="mt-2 flex flex-wrap items-center gap-2 text-[12px] leading-4 text-[var(--text-primary)]">
          <StarRow value={review.star_rating} size={20} gap={4} />
          <Dot />
          <span data-verdict={review.verdict} className="font-medium">
            <span className="sr-only">Verdict: </span>
            {VERDICT_PRESET[review.verdict] ?? VERDICT_PRESET.it_depends}
          </span>
        </p>

        {reviewPhotos(review).length ? (
          <div className="mt-4">
            <ReviewHero review={review} />
          </div>
        ) : null}

        {/* Only an author (or an administrator) can load an unpublished review.
            Since 2026-09-22 that means an administrator took it down (or it was
            rejected under the old hide-until-approved flow); the author is
            told plainly that nobody else can see it. */}
        {isOwnReview && review.published_at == null ? (
          <p
            role="status"
            className="mt-5 rounded-[12px] bg-[var(--surface-card)] px-4 py-3 text-[12px] leading-[18px] text-[var(--text-primary)] shadow-[var(--shadow-hairline-inset)]"
          >
            <span className="font-medium">
              {review.earn_eligible_status === "rejected" ? "Not published. " : "Taken down. "}
            </span>
            {review.earn_eligible_status === "rejected"
              ? "An administrator did not publish this review. Only you can see it."
              : "An administrator took it down and is taking another look. Only you can see it for now."}
            {/* QA-054: the reason the administrator gave, when they gave one — for a
                takedown, and for a review rejected before publication (the
                retest opened exactly such a notice and found no reason). */}
            {(review.earn_eligible_status === "rejected"
              ? data.author_rejection_reason
              : data.author_takedown_reason) ? (
              <span className="mt-1 block">
                <span className="font-medium">Reason: </span>
                {review.earn_eligible_status === "rejected"
                  ? data.author_rejection_reason
                  : data.author_takedown_reason}
              </span>
            ) : null}
          </p>
        ) : null}

        {/* QA-054: where a rejection notice lands. Earnings are decided
            separately from publication (§2), so a public review can still be
            one that won't earn — the author is told that, and why. */}
        {isOwnReview && review.published_at != null && review.earn_eligible_status === "rejected" ? (
          <p
            role="status"
            className="mt-5 rounded-[12px] bg-[var(--surface-card)] px-4 py-3 text-[12px] leading-[18px] text-[var(--text-primary)] shadow-[var(--shadow-hairline-inset)]"
          >
            <span className="font-medium">Won&rsquo;t earn. </span>
            Your review stays public, but an administrator decided it won&rsquo;t earn
            {data.author_rejection_reason ? `: ${data.author_rejection_reason}` : "."}
          </p>
        ) : null}

        {verified || disclosure ? (
          <div className="mt-5 flex flex-wrap items-center gap-3">
            {/* Business Rules §3: possession, not purchase — say only that. */}
            {verified ? (
              <span className="inline-flex items-center gap-1 text-[12px] text-[var(--accent-success)]">
                <SealCheck size={16} weight="fill" />
                Photo provided
              </span>
            ) : null}
            {/* X.1: shown whenever the reviewer declared a relationship. */}
            {disclosure ? (
              <span className="inline-flex items-center gap-1 rounded-[var(--radius-pill)] bg-[color-mix(in_srgb,var(--accent-trust)_12%,transparent)] px-2.5 py-1 text-[12px] font-medium text-[var(--text-primary)]">
                <Info size={14} aria-hidden="true" className="text-[var(--accent-trust)]" />
                {disclosure}
              </span>
            ) : null}
          </div>
        ) : null}

        <div className="mt-5 flex flex-col gap-5">
          {/* QA-066: the preset is in RatingMeta above; the reviewer's own
              words are the Verdict section, in 14px Italic as their quote. */}
          {review.verdict_explanation ? (
            <Section title="Verdict">
              <blockquote className="whitespace-pre-line italic">
                &ldquo;{review.verdict_explanation}&rdquo;
              </blockquote>
            </Section>
          ) : null}

          {hasPros || hasCons ? (
            <Section title="Pros & Cons">
              <div className="grid grid-cols-2 gap-4">
                <PointList kind="pro" items={review.pros ?? []} />
                <PointList kind="con" items={review.cons ?? []} />
              </div>
            </Section>
          ) : null}

          {/* `id="review-body"` is the element ReadingTelemetry observes for both
              "is the discussion in view" and the scroll read-through fraction —
              design §4.3/§4.4. The frame's "Experience" and "General info" are
              one field here (`discussion`), under the frame's first heading. */}
          <Section title="Experience">
            <p id="review-body" className="whitespace-pre-line">
              {review.discussion}
            </p>
          </Section>

          {review.target_audience ? (
            <Section title="Best for">
              <p>{review.target_audience}</p>
            </Section>
          ) : null}

          {review.anti_target_audience ? (
            <Section title="This is not for">
              <p>{review.anti_target_audience}</p>
            </Section>
          ) : null}

          {review.price_paid ? (
            <Section title="General info">
              <p>
                Paid <span className="font-medium">{peso(String(review.price_paid))}</span>
              </p>
            </Section>
          ) : null}
        </div>

        {/* Wraps rather than overflowing: with both vote counts and the
            worded "No shop link" (QA-030/031) the row is wider than a 320px
            phone, and a sideways scroll there is worse than a second line. */}
        <div className="mt-5 flex flex-wrap items-center gap-2">
          <ReviewVoteBar
            reviewId={review.id}
            helpful={review.helpful_votes}
            unhelpful={review.unhelpful_votes}
            canVote={canVote}
            readOnly={voteReadOnly}
            myVote={review.my_vote}
          />
          <a
            href="#comments"
            aria-label={`${commentCount} ${commentCount === 1 ? "comment" : "comments"}`}
            className="inline-flex h-8 shrink-0 items-center gap-1 rounded-[20px] border border-[var(--line-hairline-30)] px-3 text-[12px] leading-none text-[var(--text-primary)] no-underline hover:bg-[var(--line-hairline-10)]"
          >
            <Chats size={16} aria-hidden="true" />
            <span aria-hidden="true">{compact(commentCount)}</span>
          </a>

          {/* Hidden at `lg`: the sidebar's product card carries the Buy action
              on desktop, and two identical CTAs on one screen is a choice the
              reader has to make for no reason. */}
          {review.referral_redirect_url ? (
            <a
              href={review.referral_redirect_url}
              target="_blank"
              rel="noopener noreferrer nofollow sponsored"
              data-telemetry-outlink
              data-telemetry-review-id={review.id}
              className="ml-auto inline-flex h-8 shrink-0 items-center gap-1 rounded-[20px] border border-[var(--accent-primary)] px-[11px] text-[12px] font-light leading-none text-[var(--accent-primary)] no-underline hover:bg-[color-mix(in_srgb,var(--accent-primary)_8%,transparent)] lg:hidden"
            >
              <ShoppingBagOpen size={20} aria-hidden="true" />
              Shop
            </a>
          ) : listing ? (
            // QA-006: the product's own listing, a plain link that earns
            // nobody anything, and says so to screen readers and on hover.
            <a
              href={listing.href}
              target="_blank"
              rel="noopener noreferrer nofollow"
              title={LISTING_NOTE}
              data-testid="listing-link-mobile"
              className="ml-auto inline-flex h-8 shrink-0 items-center gap-1 rounded-[20px] border border-[var(--line-hairline-30)] px-[11px] text-[12px] font-light leading-none text-[var(--accent-primary)] no-underline hover:bg-[color-mix(in_srgb,var(--accent-primary)_8%,transparent)] lg:hidden"
            >
              <ArrowSquareOut size={18} aria-hidden="true" />
              {listing.label}
              <span className="sr-only"> — {LISTING_NOTE}</span>
            </a>
          ) : (
            // QA-031: said in words, not a greyed-out button with a hover-only
            // tooltip a phone can never show. Only a review approved to earn a
            // commission carries a shop link (Business Rules §3); one on the
            // Honesty Fund track never will, so this does not promise "yet".
            <span
              title="Shop links appear only on reviews approved to earn a commission."
              className="ml-auto inline-flex h-8 shrink-0 items-center gap-1 rounded-[20px] border border-dashed border-[var(--line-hairline-30)] px-[11px] text-[12px] font-light leading-none text-[var(--text-secondary)] lg:hidden"
            >
              <ShoppingBagOpen size={20} aria-hidden="true" />
              No shop link
              <span className="sr-only"> — shop links appear only on reviews approved to earn a commission</span>
            </span>
          )}

          <div className="lg:ml-auto">
            <ShareButton
              title={review.title}
              reviewId={review.id}
              excerpt={review.discussion}
              image={shareImageFor(review.photo_url, product?.image_url)}
              caption={
                isOwnReview
                  ? review.referral_redirect_url
                    ? "Share your post on other platforms to get more views and boost your commission."
                    : "Share your post on other platforms to get more views."
                  : null
              }
              variant="icon"
            />
          </div>

          {!isOwnReview ? <ReportDialog reviewId={review.id} canReport={canVote} hideTrigger /> : null}
        </div>
        </div>
      </article>
    </>
  );
}

/**
 * A titled block of the review card (Figma "Section/…", 7651:5849 …): the
 * label in 12px Regular trust blue on a 16px line, 12px over 14px Light on a
 * 1.5 line. Long words wrap inside the card.
 */
function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="min-w-0">
      <h2 className="text-[12px] font-normal leading-4 text-[var(--accent-trust)]">{title}</h2>
      <div className="mt-3 break-words text-[14px] font-light leading-[1.5] text-[var(--text-primary)] [overflow-wrap:anywhere]">
        {children}
      </div>
    </section>
  );
}

/**
 * One column of Pros & Cons — Figma "Attribute" (7659:5998): a 44px #f2f2f2
 * circle holding a 32px Phosphor Check or X, 8px to the point in 12px Regular.
 * The frame's 10px caption ("Price", "Portability") is an aspect the composer
 * does not collect, so it is not drawn.
 */
function PointList({ kind, items }: { kind: "pro" | "con"; items: string[] }) {
  const isPro = kind === "pro";
  if (items.length === 0) return <div />;
  return (
    <ul aria-label={isPro ? "Pros" : "Cons"} className="flex min-w-0 flex-col gap-4">
      {items.map((item, i) => (
        <li key={i} className="flex min-w-0 items-center gap-2 text-[12px] font-normal leading-4">
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-full bg-[var(--surface-app)] text-[var(--base-black)]">
            {isPro ? (
              <Check size={32} weight="light" aria-label="Pro" />
            ) : (
              <X size={32} weight="light" aria-label="Con" />
            )}
          </span>
          <span className="min-w-0 break-words [overflow-wrap:anywhere]">{item}</span>
        </li>
      ))}
    </ul>
  );
}

const TOOL =
  "flex min-w-0 flex-1 cursor-pointer flex-col items-center gap-1 rounded-[12px] bg-[var(--surface-app)] px-1 py-2.5 text-center text-[12px] leading-[normal] text-[var(--text-primary)] no-underline hover:bg-[var(--line-hairline-10)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]";

function ProductPanel({ product, tools }: { product: ReviewFull["product"]; tools: React.ReactNode }) {
  const image = product ? usablePhoto(product.image_url) : null;
  return (
    <section aria-label="Product" className="mx-2 flex flex-col gap-3 rounded-[16px] bg-[var(--surface-card)] p-3 md:mx-0">
      {product ? (
        <div className="flex min-w-0 items-center gap-2.5">
          <span className="relative h-10 w-10 shrink-0 overflow-hidden rounded-[8px] bg-[#e1e1e1]">
            {image ? <Image src={image} alt="" fill sizes="40px" className="object-cover" /> : null}
          </span>
          <span className="min-w-0 break-words text-[12px] leading-[normal] text-[var(--text-primary)] [overflow-wrap:anywhere]">
            {product.canonical_name}
          </span>
        </div>
      ) : null}
      <div className="flex gap-2">{tools}</div>
    </section>
  );
}

export default ReviewDetail;
