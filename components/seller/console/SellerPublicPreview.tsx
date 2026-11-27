import Link from "next/link";
import { Info, Storefront } from "@phosphor-icons/react/dist/ssr";

import { Chip } from "@/components/console/Chip";
import { ReviewerInitial, StarRow } from "@/components/sellers/SellerIdentity";
import { STAR_BAR_COLOUR } from "@/components/sellers/SellerRatingSummary";
import { PLATFORM_LABEL, distributionBars, percent, type SellerPlatform } from "@/components/sellers/seller-model";
import type { SellerDetail as Seller, SellerReview as Review } from "@/lib/sellers";
import { trustLevel } from "@/lib/trust";

import { agoShort } from "./overview-model";

/**
 * Screen/Seller/PublicPage (Figma 8217:23574): the store's public page as
 * buyers see it, read-only inside the console. The figures, reviews and
 * questions are the public ones (the same API the store page reads); the
 * store's responses and answers show under each with the store's name.
 *
 * Sorting is in the URL (Most helpful, Newest, Lowest rating) and shows the
 * first ten; "Open on Bluntly" is the real page, with every review.
 */

type StoreQuestion = import("@/lib/api-types").components["schemas"]["StoreQuestionOut"];

export type PublicSort = "helpful" | "newest" | "lowest";
export const PUBLIC_SORTS: { key: PublicSort; label: string }[] = [
  { key: "helpful", label: "Most helpful" },
  { key: "newest", label: "Newest" },
  { key: "lowest", label: "Lowest rating" },
];

const CARD = "rounded-[16px] border border-[var(--border-subtle)] p-5";
const SHOWN = 10;

export function sortPublic(reviews: Review[], sort: PublicSort): Review[] {
  const by = [...reviews];
  if (sort === "newest") return by.sort((a, b) => b.created_at.localeCompare(a.created_at));
  if (sort === "lowest") return by.sort((a, b) => Number(a.overall_rating) - Number(b.overall_rating) || b.created_at.localeCompare(a.created_at));
  return by.sort(
    (a, b) => (b.helpful_votes ?? 0) - (b.unhelpful_votes ?? 0) - ((a.helpful_votes ?? 0) - (a.unhelpful_votes ?? 0)) || b.created_at.localeCompare(a.created_at),
  );
}

export function SellerPublicPreview({
  storeId,
  seller,
  reviews,
  questions,
  sort,
  now,
}: {
  storeId: string;
  seller: Seller;
  reviews: Review[] | null;
  questions: StoreQuestion[] | null;
  sort: PublicSort;
  now: number;
}) {
  const s = seller.summary;
  const platform = PLATFORM_LABEL[seller.platform as SellerPlatform] ?? seller.platform;
  // The public list never carries a removed review.
  const shown = sortPublic(reviews ?? [], sort).slice(0, SHOWN);
  const bars = distributionBars(s.rating_distribution);
  const score = (v: number | null | undefined) => (v == null ? "—" : `${Number.isInteger(v) ? v : v.toFixed(1)} / 5`);
  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <h1 className="flex-1 text-[24px] font-semibold leading-none">Public page</h1>
        <Link href={`/sellers/${storeId}`} className="grid h-9 place-items-center rounded-full border border-[var(--text-primary)] px-4 text-[12px] hover:bg-[var(--surface-app)]">
          Open on Bluntly
        </Link>
      </div>
      <p className="flex items-start gap-2 rounded-[12px] bg-[var(--surface-app)] px-4 py-3 text-[14px] text-[var(--text-secondary)]">
        <Info size={18} aria-hidden className="mt-px shrink-0" />
        This is what buyers see. Your responses and store answers show under each review and question with your store name.
      </p>

      <section className={CARD} aria-label="Your store, as buyers see it">
        <div className="flex items-center gap-4">
          <span className="grid size-16 shrink-0 place-items-center rounded-[12px] bg-[var(--surface-app)]" aria-hidden>
            <Storefront size={24} />
          </span>
          <span className="flex min-w-0 flex-col gap-1">
            <span className="flex flex-wrap items-center gap-2">
              <span className="text-[20px] font-semibold leading-tight">{seller.display_name}</span>
              {seller.claim_status === "claimed" ? <Chip tone="success">Claimed by the owner</Chip> : null}
            </span>
            <span className="text-[12px] text-[var(--text-secondary)]">
              {platform} store · {seller.review_count} review{seller.review_count === 1 ? "" : "s"} on Bluntly
            </span>
          </span>
        </div>
        <dl className="mt-5 grid grid-cols-2 gap-4 border-t border-[var(--border-subtle)] pt-4 sm:grid-cols-3 xl:grid-cols-6">
          <Figure label="Overall">
            <span className="flex items-center gap-2">
              {s.overall_average != null ? s.overall_average.toFixed(1) : "—"}
              <StarRow value={s.overall_average ?? null} size={14} gap={1} />
            </span>
          </Figure>
          <Figure label="Matched the listing">{percent(s.accuracy_rate ?? null) ?? "—"}</Figure>
          <Figure label="Complete orders">{percent(s.order_completeness_rate ?? null) ?? "—"}</Figure>
          <Figure label="Would recommend">{percent(s.recommend_rate ?? null) ?? "—"}</Figure>
          <Figure label="Customer service">{score(s.customer_service_average)}</Figure>
          <Figure label="Packaging">{score(s.packaging_quality_average)}</Figure>
        </dl>
        <p className="mt-4 text-[12px] text-[var(--text-secondary)]">Owners can’t rate, vote on or review their own store.</p>
      </section>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <section aria-label="Store reviews" className="flex min-w-0 flex-col gap-3">
          <div className="flex flex-wrap items-center gap-2">
            <h2 className="flex-1 text-[16px] font-semibold leading-none">Store reviews</h2>
            <nav aria-label="Sort reviews" className="flex flex-wrap gap-2">
              {PUBLIC_SORTS.map((o) => (
                <Link
                  key={o.key}
                  href={o.key === "helpful" ? `/seller/${storeId}/public` : `/seller/${storeId}/public?sort=${o.key}`}
                  aria-current={o.key === sort ? "true" : undefined}
                  className={`grid h-9 place-items-center rounded-full border px-4 text-[14px] ${
                    o.key === sort ? "border-[var(--base-ink-800)] bg-[var(--base-ink-800)] text-white" : "border-[var(--border-subtle)] hover:bg-[var(--surface-app)]"
                  }`}
                >
                  {o.label}
                </Link>
              ))}
            </nav>
          </div>
          {reviews === null ? (
            <p role="alert" className={`${CARD} text-[14px] text-[var(--text-secondary)]`}>
              Reviews couldn’t be loaded just now.
            </p>
          ) : shown.length === 0 ? (
            <p className={`${CARD} text-[14px] text-[var(--text-secondary)]`}>No one has reviewed your store yet. Buyers’ reviews show here as they arrive.</p>
          ) : (
            <>
              {shown.map((r) => (
                <ReviewCard key={r.id} review={r} storeName={seller.display_name} now={now} />
              ))}
              {seller.review_count > shown.length ? (
                <Link href={`/sellers/${storeId}#all-reviews`} className="self-start text-[12px] text-[var(--chart-honesty-fund)] hover:underline">
                  See all {seller.review_count} reviews on Bluntly
                </Link>
              ) : null}
            </>
          )}
        </section>

        <div className="flex min-w-0 flex-col gap-4">
          <section className={CARD} aria-label="Ratings">
            <h2 className="text-[16px] font-semibold leading-none">Ratings</h2>
            <ul className="mt-4 flex flex-col gap-3">
              {bars.map((b) => (
                <li key={b.star} className="flex items-center gap-3 text-[12px]">
                  <span className="w-6 text-[var(--text-secondary)]">{b.star}★</span>
                  <span className="h-[6px] flex-1 overflow-hidden rounded-full bg-[var(--surface-app)]" aria-hidden>
                    <span className="block h-full rounded-full" style={{ width: `${b.share * 100}%`, background: STAR_BAR_COLOUR[b.star] }} />
                  </span>
                  <span className="w-8 text-right [font-variant-numeric:tabular-nums]">
                    {b.count}
                    <span className="sr-only"> reviews gave {b.star} stars</span>
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-4 text-[12px] text-[var(--text-secondary)]">Medians, so a few extreme ratings can’t swing the score.</p>
          </section>

          <section className={CARD} aria-label="Questions about this store">
            <h2 className="text-[16px] font-semibold leading-none">Questions about this store</h2>
            {questions === null ? (
              <p className="mt-4 text-[14px] text-[var(--text-secondary)]">Questions couldn’t be loaded just now.</p>
            ) : questions.length === 0 ? (
              <p className="mt-4 text-[14px] text-[var(--text-secondary)]">No one has asked about your store yet.</p>
            ) : (
              <ul className="mt-3 flex flex-col">
                {[...questions]
                  .sort((a, b) => b.created_at.localeCompare(a.created_at))
                  .slice(0, 5)
                  .map((q) => (
                    <li key={q.id} className="flex flex-col gap-1 border-t border-[var(--border-subtle)] py-4 first:border-t-0">
                      <Link href={`/questions/${q.id}`} className="text-[14px] font-medium hover:underline">
                        {q.body}
                      </Link>
                      <span className="text-[12px] text-[var(--text-secondary)]">asked by {q.asker?.username ?? q.asker?.display_name ?? "a former member"}</span>
                      {q.store_answer ? (
                        <StoreLine name={seller.display_name}>{q.store_answer.body}</StoreLine>
                      ) : (
                        <Chip tone="warning" className="mt-1 self-start font-normal">
                          No answer from the store yet
                        </Chip>
                      )}
                    </li>
                  ))}
              </ul>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}

function Figure({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <dt className="text-[12px] text-[var(--text-secondary)]">{label}</dt>
      <dd className="text-[16px] font-semibold leading-none [font-variant-numeric:tabular-nums]">{children}</dd>
    </div>
  );
}

function ReviewCard({ review: r, storeName, now }: { review: Review; storeName: string; now: number }) {
  const name = r.reviewer?.username ?? r.reviewer?.display_name ?? "Former member";
  const facts: { label: string; good: boolean }[] = [
    { label: r.accuracy ? "As listed" : "Not as listed", good: r.accuracy },
    { label: r.order_completeness ? "Complete" : "Incomplete", good: r.order_completeness },
    { label: r.would_recommend ? "Would recommend" : "Wouldn’t recommend", good: r.would_recommend },
  ];
  return (
    <article className={`${CARD} flex flex-col gap-3`}>
      <div className="flex items-start gap-3">
        <ReviewerInitial name={name} size={28} />
        <span className="flex min-w-0 flex-1 flex-col gap-0.5">
          <span className="truncate text-[14px]">{name}</span>
          {r.reviewer ? <span className="text-[12px] text-[var(--text-secondary)]">{trustLevel(r.reviewer.trust_level_name, r.reviewer.trust_stage)}</span> : null}
        </span>
        <span className="flex shrink-0 items-center gap-2">
          <StarRow value={Number(r.overall_rating)} size={16} gap={2} />
          <span className="text-[12px] text-[var(--text-secondary)]">{agoShort(r.created_at, now)}</span>
        </span>
      </div>
      {r.title ? <h3 className="text-[14px] font-medium [overflow-wrap:anywhere]">{r.title}</h3> : null}
      {r.comment ? <p className="text-[14px] [overflow-wrap:anywhere]">{r.comment}</p> : null}
      <ul className="flex flex-wrap gap-2" aria-label="Order facts">
        {facts.map((f) => (
          <li key={f.label}>
            <Chip tone={f.good ? "muted" : "warning"} className="font-normal">
              {f.label}
            </Chip>
          </li>
        ))}
      </ul>
      {r.seller_response ? <StoreLine name={storeName}>{r.seller_response}</StoreLine> : null}
    </article>
  );
}

function StoreLine({ name, children }: { name: string; children: React.ReactNode }) {
  return (
    <p className="mt-1 flex items-start gap-2 border-l border-[var(--border-subtle)] pl-3 text-[14px]">
      <span className="mt-[3px] size-4 shrink-0 rounded-full bg-[var(--accent-primary)]" aria-hidden />
      <span className="min-w-0 [overflow-wrap:anywhere]">
        <span className="font-medium">{name}</span> <span className="text-[var(--text-secondary)]">{children}</span>
      </span>
    </p>
  );
}
