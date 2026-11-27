"use client";

import Link from "next/link";
import { useCallback, useId, useRef, useState } from "react";
import {
  ArrowsDownUp,
  CheckSquare,
  DotOutline,
  Hourglass,
  Info,
  MagnifyingGlass,
  Sliders,
  Square,
  Star,
} from "@phosphor-icons/react";

import type { Question } from "@/lib/qa";
import type { SellerReview, SellerSummary } from "@/lib/sellers";

import { Checkbox, Radio, Section, Sheet } from "@/components/search/FilterSheet";
import { SortMenu } from "@/components/search/SortMenu";
import { HonestyScore } from "@/components/ui/HonestyScore";
import { STAR_EMPTY, starColor } from "@/components/ui/star-ladder";

import { AskSellerQuestionForm } from "./AskSellerQuestionForm";
import { ReviewerInitial } from "./SellerIdentity";
import { STAR_BAR_COLOUR } from "./SellerRatingSummary";
import { SellerReviewCard } from "./SellerReviewCard";
import {
  distributionBars,
  filterSellerReviews,
  SELLER_REVIEW_SORT_SECTIONS,
  sharePercent,
  shortAge,
  sortSellerReviews,
  type SellerReviewSort,
} from "./seller-model";
import { SEARCH_FOCUS } from "@/components/ui/search-styles";

/**
 * The store page's "All reviews" block, built to the lower half of Figma
 * "Seller Page - Review" (4218:2148) and "Seller Page - Questions", read
 * 2026-09-14.
 *
 * A 20px green star beside the average in 20px SemiBold; 26px down, "All
 * reviews" in 12px Light and the count in 10px Light; 17px down, the disclaimer
 * on #bacce6 — a 16px Info glyph 12px in and 14px type on a 22px line; 16px
 * down, the star filter in a card like the rating card (30% ink outline, radius
 * 16), rows on a 27px pitch of a 20px CheckSquare, the "5 star" label and share
 * in 10px Light and a 12px bar between; 24px down, the keyword bar; 20px down,
 * Reviews / Questions in 12px over a full-bleed 1px rule 13px below them; list
 * items 40px apart.
 *
 * The filter and search are real, and they run over the reviews this page
 * loaded — the newest 100, the API's ceiling. When a store has more, the list
 * says so rather than implying the filter saw everything.
 *
 * QA-057, re-read 2026-09-24: under the Reviews / Questions tabs the frame
 * draws the "All filters" and "Sort" pills (Group 691, 4281:870) — the search
 * page's pills and sheets. All filters holds the rating (the same ticks as the
 * card above, one state) and Time; Sort holds By date (Latest / Oldest), the
 * rating, and photos first. Every one filters or orders for real. Sort opens
 * the search page's dropdown Menu (SortMenu), not a sheet (owner 2026-10-07),
 * and a choice applies at once.
 *
 * NOT RENDERED: "Read more." in the disclaimer (no page explains it), "Top
 * mentions" chips (seller reviews carry no topics), and per-review votes and
 * threaded replies (a product decision, not a UI gap: QA-043).
 */

const ALL_STARS = [5, 4, 3, 2, 1];

type Tab = "reviews" | "questions";

const QUIET = "text-[12px] font-light leading-[18px] text-[var(--text-secondary)]";

// The search page's pill (SearchFilterBar): 32px, 11px sides inside a 1px
// outline, radius 16, a 16px glyph 4px before 12px text.
const PILL =
  "inline-flex h-8 shrink-0 cursor-pointer items-center gap-1 whitespace-nowrap rounded-[var(--radius-md)] px-[11px] text-[12px] leading-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]";
const PILL_OFF = "border border-[var(--text-primary)] text-[var(--text-primary)]";
const PILL_ON = "border border-[var(--accent-primary)] text-[var(--accent-primary)]";

export function SellerReviewsSection({
  sellerId,
  summary,
  reviews,
  questions,
  claimed,
  signedIn,
  canModerate,
  isOwner = false,
  viewerId = null,
  now,
}: {
  sellerId: string;
  summary: SellerSummary;
  /** Null when the reviews could not be loaded. */
  reviews: SellerReview[] | null;
  /** Null when the questions could not be loaded. */
  questions: Question[] | null;
  claimed: boolean;
  signedIn: boolean;
  canModerate: boolean;
  /** The viewer is this store's claimed owner (QA-043). */
  isOwner?: boolean;
  /** The signed-in viewer's id (QA-043 votes and replies), or null. */
  viewerId?: string | null;
  /** When the server rendered the page, for every age (see `shortAge`). */
  now: number;
}) {
  const keywordId = useId();
  const tabsId = useId();
  const [stars, setStars] = useState<number[]>(ALL_STARS);
  const [keyword, setKeyword] = useState("");
  const [sort, setSort] = useState<SellerReviewSort>("newest");
  const [period, setPeriod] = useState<"all" | "year" | "month">("all");
  const [sheet, setSheet] = useState<"filters" | "sort" | null>(null);
  const [draftStars, setDraftStars] = useState<number[]>(ALL_STARS);
  const [draftPeriod, setDraftPeriod] = useState<"all" | "year" | "month">("all");
  const sheetTrigger = useRef<HTMLButtonElement | null>(null);
  const [sortAnchor, setSortAnchor] = useState<HTMLElement | null>(null);
  const [tab, setTab] = useState<Tab>("reviews");
  const tabRefs = useRef<Record<Tab, HTMLButtonElement | null>>({ reviews: null, questions: null });

  const bars = distributionBars(summary.rating_distribution);
  const visible =
    reviews === null ? [] : sortSellerReviews(filterSellerReviews(reviews, { stars, keyword, period }), sort);

  const openSheet = (kind: "filters" | "sort", from: HTMLButtonElement) => {
    sheetTrigger.current = from;
    setSortAnchor(kind === "sort" ? from : null);
    // Every opening starts from what is applied, so a cancelled change is gone.
    setDraftStars(stars);
    setDraftPeriod(period);
    setSheet(kind);
  };
  const closeSheet = useCallback(() => {
    setSheet(null);
    sheetTrigger.current?.focus();
  }, []);
  const filtered = stars.length !== ALL_STARS.length || period !== "all";
  const partial = reviews !== null && summary.review_count > reviews.length;
  const average = summary.overall_average;

  const toggleStar = (star: number) =>
    setStars((current) => (current.includes(star) ? current.filter((s) => s !== star) : [...current, star]));

  const selectTab = (next: Tab) => {
    setTab(next);
    tabRefs.current[next]?.focus();
  };

  const tabButton = (key: Tab, label: string) => (
    <button
      ref={(el) => {
        tabRefs.current[key] = el;
      }}
      type="button"
      role="tab"
      id={`${tabsId}-${key}`}
      aria-selected={tab === key}
      aria-controls={`${tabsId}-${key}-panel`}
      tabIndex={tab === key ? 0 : -1}
      onClick={() => setTab(key)}
      onKeyDown={(e) => {
        if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
          e.preventDefault();
          selectTab(key === "reviews" ? "questions" : "reviews");
        }
      }}
      className={`flex cursor-pointer pb-[13px] text-[12px] leading-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)] ${
        tab === key ? "text-[var(--accent-primary)]" : "text-[var(--text-primary)] hover:text-[var(--accent-primary)]"
      }`}
    >
      {label}
    </button>
  );

  return (
    <section id="all-reviews" aria-labelledby={`${tabsId}-heading`} className="scroll-mt-24 text-[var(--text-primary)]">
      <p className="flex items-center gap-1">
        <Star size={20} weight="fill" aria-hidden="true" style={{ color: average === null ? STAR_EMPTY : starColor(average) }} />
        <span className="text-[20px] font-semibold leading-none">
          {average === null ? "—" : average.toFixed(1)}
        </span>
      </p>
      <h2 id={`${tabsId}-heading`} className="mt-[26px] text-[12px] font-light leading-none">
        All reviews
      </h2>
      <p className="mt-1.5 text-[10px] font-light leading-none">
        {summary.review_count} {summary.review_count === 1 ? "review" : "reviews"}
      </p>

      <p className="mt-[17px] flex gap-2 rounded-[8px] bg-[#bacce6] p-3 text-[14px] leading-[22px]">
        <Info size={16} aria-hidden="true" className="mt-1 shrink-0" />
        Reviews are the opinions of individual users and not of Bluntly.ph.
      </p>

      <fieldset className="mt-4 rounded-[16px] border border-[var(--line-hairline-30)] pb-[19px] pl-[26px] pr-4 pt-[22px]">
        <legend className="sr-only">Show reviews with</legend>
        <ul className="flex flex-col gap-[7px]">
          {bars.map((bar) => {
            const checked = stars.includes(bar.star);
            return (
              <li key={bar.star}>
                <label className="flex cursor-pointer items-center">
                  {/* The frame's 20px CheckSquare. The native input stays on top
                      of it, so keyboard and screen readers get a real checkbox. */}
                  <span className="relative grid h-5 w-5 shrink-0 place-items-center">
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleStar(bar.star)}
                      className="peer absolute inset-0 m-0 cursor-pointer appearance-none rounded-[3px] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-[var(--accent-primary)]"
                    />
                    {checked ? (
                      <CheckSquare size={20} aria-hidden="true" className="pointer-events-none" />
                    ) : (
                      <Square size={20} aria-hidden="true" className="pointer-events-none" />
                    )}
                  </span>
                  <span className="ml-1 w-7 shrink-0 whitespace-nowrap text-[10px] font-light leading-none">
                    {bar.star} star
                  </span>
                  <span className="ml-3 h-3 flex-1 overflow-hidden rounded-[10px] bg-[var(--base-gray-200)]">
                    <span
                      className="block h-full rounded-[10px]"
                      style={{ width: `${bar.share * 100}%`, background: STAR_BAR_COLOUR[bar.star] }}
                    />
                  </span>
                  <span className="ml-2 w-[26px] shrink-0 text-right text-[10px] font-light leading-none">
                    {sharePercent(bar.share)}
                  </span>
                </label>
              </li>
            );
          })}
        </ul>
      </fieldset>

      <div className="relative mt-6">
        <label htmlFor={keywordId} className="sr-only">
          Search reviews by keyword
        </label>
        <MagnifyingGlass
          size={16}
          aria-hidden="true"
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-[var(--text-primary)]"
        />
        <input
          id={keywordId}
          type="search"
          value={keyword}
          onChange={(e) => setKeyword(e.target.value)}
          placeholder="Search by keyword"
          className={`h-8 w-full rounded-[var(--radius-pill)] border border-[var(--text-primary)] bg-transparent pl-9 pr-4 text-[16px] font-light text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] md:text-[12px] ${SEARCH_FOCUS}`}
        />
      </div>

      <div
        role="tablist"
        aria-label="Store content"
        className="-mx-4 mt-5 flex gap-8 border-b border-[var(--line-hairline-10)] px-4"
      >
        {tabButton("reviews", "Reviews")}
        {tabButton("questions", "Questions")}
      </div>

      <div
        role="tabpanel"
        id={`${tabsId}-reviews-panel`}
        aria-labelledby={`${tabsId}-reviews`}
        hidden={tab !== "reviews"}
        className="mt-3"
      >
        {/* The frame's pills, 12px under the tab rule, as on /search. */}
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="button"
            aria-haspopup="dialog"
            aria-expanded={sheet === "filters"}
            onClick={(e) => openSheet("filters", e.currentTarget)}
            className={`${PILL} ${filtered ? PILL_ON : PILL_OFF}`}
          >
            <Sliders size={16} aria-hidden="true" className="rotate-90" />
            All filters
          </button>
          <button
            type="button"
            aria-haspopup="menu"
            aria-expanded={sheet === "sort"}
            onClick={(e) => openSheet("sort", e.currentTarget)}
            className={`${PILL} ${sort !== "newest" ? PILL_ON : PILL_OFF}`}
          >
            <ArrowsDownUp size={16} aria-hidden="true" />
            Sort
          </button>
          {period !== "all" ? (
            <>
              <span aria-hidden="true" className="h-[26px] w-px shrink-0 bg-[var(--line-hairline-30)]" />
              <button
                type="button"
                aria-haspopup="dialog"
                aria-label={`${period === "year" ? "Past year" : "Past month"}. Change filters`}
                onClick={(e) => openSheet("filters", e.currentTarget)}
                className={`${PILL} bg-[var(--accent-primary)] text-[var(--text-on-brand)]`}
              >
                <Hourglass size={16} aria-hidden="true" />
                {period === "year" ? "Past year" : "Past month"}
              </button>
            </>
          ) : null}
        </div>

        <div className="mt-6">
          {reviews === null ? (
            <p className={QUIET}>Reviews could not be loaded right now.</p>
          ) : reviews.length === 0 ? (
            <p className={QUIET}>
              Nobody has rated this seller yet.{" "}
              {/* Underlined: inside a sentence, colour alone did not mark it as a link
                  (1.85:1 against the text around it; Lighthouse link-in-text-block). */}
              <Link href={`/sellers/rate?seller=${sellerId}`} className="text-[var(--accent-primary)] underline underline-offset-2">
                Be the first
              </Link>
              .
            </p>
          ) : (
            <>
              <p aria-live="polite" className={QUIET}>
                {visible.length === reviews.length && !partial
                  ? `${visible.length} ${visible.length === 1 ? "review" : "reviews"}`
                  : `${visible.length} of ${partial ? `the newest ${reviews.length}` : reviews.length} reviews`}
              </p>
              {visible.length === 0 ? (
                <p className={`mt-4 ${QUIET}`}>No reviews match. Tick more stars or change the keyword.</p>
              ) : (
                <ul className="mt-4 flex flex-col gap-10">
                  {visible.map((review) => (
                    <SellerReviewCard
                      key={review.id}
                      review={review}
                      canModerate={canModerate}
                      isOwner={isOwner}
                      viewerId={viewerId}
                      now={now}
                    />
                  ))}
                </ul>
              )}
            </>
          )}
        </div>
      </div>

      {sheet === "filters" ? (
        <Sheet
          title="All filters"
          icon={<Sliders size={28} aria-hidden="true" className="rotate-90" />}
          submitLabel="Filter Reviews"
          onClose={closeSheet}
          onReset={() => {
            setStars(ALL_STARS);
            setPeriod("all");
            closeSheet();
          }}
          onSubmit={() => {
            setStars(draftStars);
            setPeriod(draftPeriod);
            closeSheet();
          }}
        >
          <Section heading="Rating" info="The same ticks as the rating card: only the stars you keep are shown.">
            {ALL_STARS.map((star) => (
              <Checkbox
                key={star}
                name="stars"
                value={String(star)}
                label={`${star} star`}
                checked={draftStars.includes(star)}
                onChange={(_, on) =>
                  setDraftStars((current) => (on ? [...new Set([...current, star])] : current.filter((s) => s !== star)))
                }
              />
            ))}
          </Section>
          <Section heading="Time" info="Shows only what was posted within the period you pick.">
            {(
              [
                ["all", "All time"],
                ["year", "Past year"],
                ["month", "Past month"],
              ] as const
            ).map(([value, label]) => (
              <Radio
                key={value}
                name="period"
                value={value}
                label={label}
                checked={draftPeriod === value}
                onChange={() => setDraftPeriod(value)}
              />
            ))}
          </Section>
        </Sheet>
      ) : null}

      {sheet === "sort" && sortAnchor ? (
        <SortMenu
          label="Sort reviews"
          anchor={sortAnchor}
          sections={SELLER_REVIEW_SORT_SECTIONS.map((section) => ({
            heading: section.heading.replace(/:$/, ""),
            options: section.options,
          }))}
          value={sort}
          onChoose={(next) => {
            setSort(next);
            closeSheet();
          }}
          onClose={closeSheet}
        />
      ) : null}

      <div
        role="tabpanel"
        id={`${tabsId}-questions-panel`}
        aria-labelledby={`${tabsId}-questions`}
        hidden={tab !== "questions"}
        className="mt-6"
      >
        <p className={QUIET}>
          {claimed
            ? "Ask the store directly. Its replies carry the Claimed Profile mark."
            : "Nobody has claimed this store yet, so other buyers are the ones who can answer."}
        </p>
        <AskSellerQuestionForm sellerId={sellerId} signedIn={signedIn} />
        {questions === null ? (
          <p className={`mt-4 ${QUIET}`}>Questions could not be loaded right now.</p>
        ) : questions.length === 0 ? (
          <p className={`mt-4 ${QUIET}`}>No questions yet.</p>
        ) : (
          // "Seller Page - Questions": the asker's 36px disc with the same
          // byline as a review, then the question in 14px Bold. NOT RENDERED:
          // the vote / Reply / Share row and the store's nested reply — the list
          // API carries no answers, so each question links to its own page.
          <ul className="mt-6 flex flex-col gap-10">
            {questions.map((q) => {
              const asker = q.asker?.username ?? q.asker?.display_name ?? "A buyer";
              return (
                <li key={q.id}>
                  <Link href={`/questions/${q.id}`} className="block text-[var(--text-primary)] no-underline">
                    <span className="flex items-center gap-2">
                      <ReviewerInitial name={asker} />
                      <span className="min-w-0">
                        <span className="flex flex-wrap items-center text-[12px] font-light leading-4">
                          <span className="truncate">{asker}</span>
                          {q.asker ? (
                            <>
                              <DotOutline size={16} aria-hidden="true" className="shrink-0 text-[var(--base-gray-400)]" />
                              <HonestyScore
                                score={q.asker.reputation_score}
                                levelName={q.asker.trust_level_name}
                                stage={q.asker.trust_stage}
                              />
                              {q.asker.trust_level_name ? (
                                <>
                                  <DotOutline size={16} aria-hidden="true" className="shrink-0 text-[var(--base-gray-400)]" />
                                  <span aria-hidden="true">{q.asker.trust_level_name}</span>
                                </>
                              ) : null}
                            </>
                          ) : null}
                        </span>
                        <span className="block text-[12px] font-extralight leading-[18px]">
                          <time dateTime={q.created_at}>{shortAge(q.created_at, now)}</time>
                        </span>
                      </span>
                    </span>
                    <span className="mt-3 block text-[14px] font-bold leading-[21px]">{q.body}</span>
                    <span className="mt-1 block text-[12px] font-light leading-[18px] text-[var(--text-secondary)]">
                      {q.answer_count} {q.answer_count === 1 ? "answer" : "answers"}
                    </span>
                  </Link>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}

export default SellerReviewsSection;
