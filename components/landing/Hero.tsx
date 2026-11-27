import { ArrowRight, DotOutline, MagnifyingGlass } from "@phosphor-icons/react/dist/ssr";

import { graphPaper } from "@/components/ui/graph-paper";
import { FEATURED_REVIEW } from "@/lib/landing-data";
import type { FeaturedData } from "@/lib/reviews";

import { ReviewQuoteCard } from "@/components/reviews/ReviewQuoteCard";
import { SEARCH_FOCUS } from "@/components/ui/search-styles";

/**
 * Landing hero, built to Figma "Mobile Landing Page" (1902:1504), read from the
 * file on 2026-09-14.
 *
 * Phone values, status bar excluded: the frame's own graph-paper image ("image
 * 15") as a 350x568 crop at 10%; copy 32px under the 72px bar — 32px SemiBold
 * with the period in brand orange, a 12px Light line at 70% ink 4px below; 32px
 * down, a 56px field with a 10% hairline, a 20px magnifier at 30% ink 14px in,
 * the 12px Light placeholder 44px in, and a 32px orange disc 8px from the right
 * with a 20px arrow; 44px down, the tilted review card group, 450px tall because
 * the question pill sits 218px under the card at the left.
 *
 * The hero's annotations follow the file again. The owner corrected the hero
 * group in Figma on 2026-09-16 and asked for it copied one to one, which
 * replaced the interim placement we had been given verbally:
 *
 *   "How noisy is it?"     over the card's TOP-RIGHT   (frame x244 y4)
 *   "Earned ₱45.50 today"  on the card's BOTTOM-LEFT   (frame x0 y185)
 *
 * Both are positioned against the card's own box, so they travel with the
 * card and are never positioned against the viewport.
 *
 * From `md` up there is no frame: the two-column split starts at 768px, and the
 * pills sit on the card. The split used to wait for 1024px while the header had
 * already switched to its desktop form, stranding a narrow column in a wide
 * shell (QA's 768px pass).
 */
export function Hero({ featured }: { featured: FeaturedData }) {
  return (
    // `overflow-x-clip`: the tilted stack reaches the phone's right edge, and a
    // pixel past it must not become a sideways scroll.
    <section className="relative overflow-x-clip">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute left-4 top-[-6px] h-[568px] w-[350px] opacity-10 md:hidden"
        style={graphPaper(350)}
      />
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 hidden [mask-image:linear-gradient(to_bottom,black,transparent)] md:block"
        style={{
          backgroundImage:
            "linear-gradient(rgba(32,32,32,0.05) 1px, transparent 1px), linear-gradient(90deg, rgba(32,32,32,0.05) 1px, transparent 1px)",
          backgroundSize: "28px 28px",
        }}
      />

      <div className="relative mx-auto grid w-full max-w-[72rem] gap-11 px-4 pt-8 sm:px-6 md:grid-cols-2 md:items-center md:gap-8 md:px-8 md:py-14 lg:min-h-[86vh] lg:gap-16 lg:px-10 lg:py-20">
        <div className="animate-fade-up">
          {/* Desktop scales the same type up rather than restyling it, so the
              web version stays the mobile design at a larger size. */}
          <h1 className="text-[32px] font-semibold leading-[normal] text-[var(--text-primary)] md:text-[40px] lg:text-[56px]">
            Finally.
            <br />
            Honest reviews<span className="text-[var(--accent-primary)]">.</span>
          </h1>
          <p className="mt-1 text-[12px] font-light leading-none text-[rgba(32,32,32,0.7)] lg:text-[14px] lg:leading-normal">
            No sponsorships. No bias. Ever.
          </p>

          {/* Ask-anything search — posts to the search page. */}
          <form action="/search" role="search" className="relative mt-8 max-w-[34rem]">
            <MagnifyingGlass
              size={20}
              className="pointer-events-none absolute left-[14px] top-1/2 -translate-y-1/2 text-[var(--line-hairline-30)]"
            />
            <input
              type="search"
              name="q"
              placeholder="Search or ask anything"
              aria-label="Search or ask anything"
              className={`h-14 w-full rounded-[32px] border border-[rgba(32,32,32,0.1)] bg-[var(--surface-app)] pl-11 pr-12 text-[12px] font-light text-[var(--text-primary)] outline-none placeholder:text-[rgba(32,32,32,0.4)] lg:text-[14px] ${SEARCH_FOCUS}`}
            />
            <button
              type="submit"
              aria-label="Search"
              className="absolute right-2 top-1/2 grid h-8 w-8 -translate-y-1/2 place-items-center rounded-full bg-[var(--accent-primary)] text-[var(--text-on-brand)] hover:bg-[var(--accent-primary-strong)]"
            >
              <ArrowRight size={20} />
            </button>
          </form>
        </div>

        {/* 209px: the frame's card group (5446:5126) is 375x209 and the Earned
            pill ends exactly on its foot. Group 812 (4512:4688) now draws a
            flat ReviewQuoteCard (7804:9363): the author row, the review's title
            in quotes, its reactions; the reader's question pill over its
            top-right corner (x244 y4) and the Earned pill 185px down at the
            left. The pills are illustrative copy, as before. */}
        <div className="animate-fade-up delay-2 relative mx-auto h-[209px] w-full max-w-[358px] md:h-auto md:max-w-[26rem] md:pb-6 md:pt-6">
          <ReviewQuoteCard
            username={featured.username ?? featured.author}
            avatarUrl={featured.avatarUrl}
            age={featured.ageLabel}
            levelName={featured.trust}
            stage={featured.trust ? featured.trustStage : null}
            score={featured.trustScore}
            title={featured.title}
            subject={featured.product}
            upvotes={featured.upvotes}
            comments={featured.comments}
            href={featured.id ? `/reviews/${featured.id}` : undefined}
          />
          <span className="absolute right-0 top-1 inline-flex h-6 items-center whitespace-nowrap rounded-[12px] bg-[var(--surface-app)] pl-1 pr-3 text-[10px] leading-none text-[var(--text-primary)] shadow-[var(--shadow-sheet)] md:top-7">
            <DotOutline size={16} aria-hidden="true" className="text-[var(--accent-primary)]" />
            &ldquo;{FEATURED_REVIEW.question}&rdquo;
          </span>
          <span className="absolute left-0 top-[185px] inline-flex h-6 items-center whitespace-nowrap rounded-[12px] bg-[var(--accent-primary)] pl-1 pr-3 text-[10px] leading-none text-[var(--text-on-brand)] shadow-[var(--shadow-sheet)] md:static md:mt-3">
            <DotOutline size={16} aria-hidden="true" />
            {FEATURED_REVIEW.earned}
          </span>
        </div>
      </div>
    </section>
  );
}

export default Hero;
