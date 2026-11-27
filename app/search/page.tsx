import type { Metadata } from "next";
import Link from "next/link";
import { CaretLeft, ChatCircle, MagnifyingGlass, Storefront, UsersThree } from "@phosphor-icons/react/dist/ssr";

import { PersonResultRow } from "@/components/search/PersonResultRow";
import { QuestionMatch } from "@/components/search/QuestionMatch";
import { SearchProductBar } from "@/components/search/SearchProductBar";
import { QuestionResultRow } from "@/components/search/QuestionResultRow";
import { SellerResultRow } from "@/components/sellers/SellerResultRow";
import { RememberSearch } from "@/components/search/RememberSearch";
import { SearchAutocomplete } from "@/components/search/SearchAutocomplete";
import { SearchFilterBar } from "@/components/search/SearchFilterBar";
import { SearchTabs, type SearchTab } from "@/components/search/SearchTabs";
import {
  BUDGET_STEPS,
  budgetLabel,
  LENS_LABEL,
  parseAnswerWindow,
  parseBudget,
  parseClaimed,
  parseFlag,
  parseCategories,
  parseLens,
  parsePeriod,
  parsePlatform,
  parseQuestionSort,
  parseReviewSort,
  parseSellerRating,
  parseStars,
  STAR_GROUPS,
  ANSWER_WINDOW_LABEL,
  parseSellerSort,
  parseTrust,
  searchTabHref,
  SELLER_SORT_LABEL,
  toggleCategory,
  type SearchState,
  type SellerSort,
} from "@/components/search/search-tabs-model";
import { ReviewVoteBar } from "@/components/review/ReviewVoteBar";
import { ShareButton } from "@/components/review/ShareButton";
import { ReviewQuoteCard } from "@/components/reviews/ReviewQuoteCard";
import { Unavailable } from "@/components/site/Unavailable";
import { PageNumbers, countLine } from "@/components/site/PageNumbers";
import {
  BrowseLayout,
  RAIL_ACTION,
  RAIL_LABEL,
  RailGroup,
  TakePartGroup,
} from "@/components/site/BrowseRails";
import { QuickActions } from "@/components/site/QuickActions";
import { SiteFooter } from "@/components/site/SiteFooter";
import { SiteHeader, type HeaderUser } from "@/components/site/SiteHeader";
import { CATEGORIES } from "@/lib/landing-data";
import { getUser } from "@/lib/dal";
import { getQuestionDetail, getQuestions, type Question, type QuestionDetail } from "@/lib/qa";
import { resolveSearchProduct } from "@/lib/search-product";
import { searchRequests, type RequestItem } from "@/lib/requests";
import { getReviewPage, getReviewVariants, splitHeadline } from "@/lib/reviews";
import { getSessionToken } from "@/lib/session";
import { searchSellers } from "@/lib/sellers";
import { searchPeople } from "@/lib/people";
import { SEARCH_FOCUS } from "@/components/ui/search-styles";

export const metadata: Metadata = {
  title: "Search — bluntly",
  // Results pages are not documents: every filter and query is a new URL.
  // Backs up the robots.txt disallow for crawlers that ignore it; `follow`
  // keeps the reviews it links to discoverable.
  robots: { index: false, follow: true },
};

/** The rail's category links: the taxonomy reviews are actually filed under. */
const RAIL_CATEGORIES = CATEGORIES.filter((c) => c.slug !== "trending");

const SELLER_SORTS: SellerSort[] = ["ranked", "reviews", "name"];

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{
    q?: string;
    category?: string | string[];
    from?: string;
    tab?: string;
    sort?: string;
    period?: string;
    platform?: string;
    claimed?: string;
    lens?: string;
    trust?: string;
    max_price?: string;
    /** The filter sheet's Rating, Show only and Variant (Figma 7762:9999). */
    stars?: string;
    photos?: string;
    verified?: string;
    recommends?: string;
    variant?: string;
    /** Sheet/Filter sellers' Rating and Answers buyers (8462:36591). */
    rating?: string;
    answers?: string;
    /** The product picked in the product bar's Switch sheet. */
    product?: string;
    /** The Reviews tab's page (MQA-036). */
    page?: string;
  }>;
}) {
  const raw = await searchParams;
  const {
    q = "",
    category,
    from,
    tab,
    sort: rawSort,
    period: rawPeriod,
    platform: rawPlatform,
    claimed,
    lens: rawLens,
    trust: rawTrust,
    max_price: rawMaxPrice,
    stars: rawStars,
    photos,
    verified,
    recommends,
    variant: rawVariant,
    rating: rawRating,
    answers: rawAnswers,
    product: pickedProduct,
    page: rawPage,
  } = raw;
  // MQA-036: the Reviews tab pages through every match, 24 at a time. The API
  // reads at most 1000 deep, so the last reachable page is 42.
  const REVIEWS_PER_PAGE = 24;
  const REVIEW_PAGES_MAX = Math.floor(1000 / REVIEWS_PER_PAGE) + 1;
  const reviewsPage = Math.min(REVIEW_PAGES_MAX, Math.max(1, Math.floor(Number(rawPage)) || 1));
  const activeTab: SearchTab =
    tab === "questions" ? "questions" : tab === "sellers" ? "sellers" : tab === "people" ? "people" : "reviews";
  // `sort` means the order of whichever tab is showing (search-tabs-model).
  const sort = parseReviewSort(activeTab === "reviews" ? rawSort : undefined);
  const categories = parseCategories(category, RAIL_CATEGORIES.map((c) => c.slug));
  const period = parsePeriod(rawPeriod);
  const state: SearchState = {
    q,
    from,
    categories,
    sort,
    period,
    lens: parseLens(rawLens),
    trust: parseTrust(rawTrust),
    maxPrice: parseBudget(rawMaxPrice),
    stars: parseStars(rawStars),
    photos: parseFlag(photos),
    verified: parseFlag(verified),
    recommends: parseFlag(recommends),
    variant: rawVariant?.trim().slice(0, 120) || undefined,
    questionSort: parseQuestionSort(activeTab === "questions" ? rawSort : undefined),
    platform: parsePlatform(rawPlatform),
    claimed: parseClaimed(claimed),
    minRating: parseSellerRating(rawRating),
    answers: parseAnswerWindow(rawAnswers),
    sellerSort: parseSellerSort(activeTab === "sellers" ? rawSort : undefined),
  };
  const activeCategories = categories
    .map((slug) => CATEGORIES.find((c) => c.slug === slug))
    .filter((c): c is (typeof CATEGORIES)[number] => Boolean(c));
  const searching = Boolean(
    q.trim() || categories.length || state.lens || state.trust || state.maxPrice ||
      state.stars?.length || state.photos || state.verified || state.recommends,
  );
  // Arrived by tapping a tile on /categories. That makes /categories the
  // meaningful "up" destination — both for the back link and for clearing the
  // category, which otherwise dead-ends on /search with no route back (BUG-011).
  const fromCategories = from === "categories";

  // Parallel: the viewer and the results are independent (see app/page.tsx).
  // Only the active tab's results are fetched — the other tab is a separate URL
  // and will fetch its own when it is visited.
  // The product the search names (Figma Mobile Search v10B / Questions v6):
  // first, because the Questions tab's results depend on it.
  const resolution =
    q.trim() && (activeTab === "reviews" || activeTab === "questions")
      ? await resolveSearchProduct(q, pickedProduct ?? null)
      : null;
  const chosen = resolution?.chosen ?? null;
  // The lists narrow to the product only once the reader picked it (Switch),
  // or, on Questions, when the search carries question words beside the
  // product's name; otherwise the text search stands and the bar summarises
  // its best match.
  const reviewProduct = chosen && pickedProduct === chosen.product.id ? chosen.product.id : null;
  const questionTerms = resolution?.rest ?? "";
  // Signed in, the rows carry the reader's own votes (QA-027/028).
  const sessionToken = await getSessionToken();
  const reviewFilters = {
    q: reviewProduct ? undefined : q,
    product_id: reviewProduct ?? undefined,
    categories,
    period,
    lens: state.lens,
    trust: state.trust,
    maxPrice: state.maxPrice,
    stars: state.stars,
    photos: state.photos,
    verified: state.verified,
    recommends: state.recommends,
    // A variant names one product's option: it applies only with that product.
    variant: reviewProduct ? state.variant : undefined,
  };
  const [me, reviewPage, questions, sellers, people, requests] = await Promise.all([
    getUser().catch(() => null),
    // The page and its total in one call (GET /reviews/feed/page).
    activeTab === "reviews"
      ? getReviewPage({ ...reviewFilters, sort, limit: REVIEWS_PER_PAGE, offset: (reviewsPage - 1) * REVIEWS_PER_PAGE, token: sessionToken })
      : Promise.resolve(null),
    activeTab === "questions"
      ? chosen && (questionTerms || reviewProduct)
        ? getQuestions(chosen.product.id, {
            q: questionTerms || undefined,
            limit: questionTerms ? 4 : 24,
            period,
            sort: state.questionSort,
          })
        : getQuestions(undefined, { q, limit: 24, period, sort: state.questionSort })
      : Promise.resolve(null),
    activeTab === "sellers"
      ? searchSellers(q, 24, {
          platform: state.platform,
          claimed: state.claimed,
          minRating: state.minRating,
          answers: state.answers,
          sort: state.sellerSort,
        })
      : Promise.resolve(null),
    activeTab === "people" ? searchPeople(q, 24) : Promise.resolve(null),
    // A review request stays findable after its Best Answer is picked: it
    // leaves the board, never search (dev/QA sync 2026-09-29).
    activeTab === "questions" && q ? searchRequests(q) : Promise.resolve([] as RequestItem[]),
  ]);
  const results = reviewPage?.cards ?? null;
  const reviewTotal = reviewPage?.total ?? null;
  // The Variant chips: only for one chosen product, and only the variants its
  // reviewers named.
  const variants = activeTab === "reviews" && reviewProduct ? await getReviewVariants(reviewProduct) : [];
  // Every query parameter as it came, with only the page changed.
  const reviewPageHref = (n: number) => {
    const params = new URLSearchParams();
    for (const [key, value] of Object.entries(raw)) {
      if (key === "page" || value === undefined) continue;
      for (const v of Array.isArray(value) ? value : [value]) params.append(key, v);
    }
    if (n > 1) params.set("page", String(n));
    const qs = params.toString();
    return qs ? `/search?${qs}` : "/search";
  };
  const reviewPages = reviewTotal === null ? 1 : Math.min(REVIEW_PAGES_MAX, Math.max(1, Math.ceil(reviewTotal / REVIEWS_PER_PAGE)));
  // ListHeader/Reviews under the product bar: "128 reviews" (7702:7593).
  const reviewHeader =
    activeTab === "reviews" && chosen && reviewTotal !== null
      ? `${reviewTotal.toLocaleString("en-PH")} ${reviewTotal === 1 ? "review" : "reviews"}`
      : null;
  const user: HeaderUser = me ? { username: me.username, avatarUrl: me.avatar_url, role: me.role } : null;
  // Questions v6: the best match's top answer, or the product's latest
  // questions when the search's question words match none.
  const matching = activeTab === "questions" && chosen && questionTerms;
  const [bestMatch, related]: [QuestionDetail | null, Question[]] = matching
    ? await Promise.all([
        questions?.[0] ? getQuestionDetail(questions[0].id) : Promise.resolve(null),
        // The product's own questions fill "Similar questions" (or, with no
        // match, "Related questions") up to the frame's three.
        getQuestions(chosen.product.id, { limit: 4 }).then((r) => r ?? []),
      ])
    : [null, []];
  const baseQuery = (() => {
    const params = new URLSearchParams();
    if (q) params.set("q", q);
    if (activeTab !== "reviews") params.set("tab", activeTab);
    return params.toString();
  })();
  // eslint-disable-next-line react-hooks/purity -- read once per request, on the server
  const renderedAt = Date.now();

  const heading = q
    ? `Results for “${q}”`
    : activeCategories.length
      ? activeCategories.map((c) => c.label).join(", ")
      : activeTab === "questions"
        ? "Recent questions"
        : activeTab === "sellers"
          ? "Sellers"
          : activeTab === "people"
            ? "People"
            : state.lens
              ? `${LENS_LABEL[state.lens]} reviews`
              : // Says the order actually applied: "Trending" is now a lens of its own.
                sort === "newest"
                ? "Latest reviews"
                : sort === "oldest"
                  ? "Oldest reviews"
                  : "Most helpful reviews";

  return (
    <div className="flex min-h-dvh flex-col bg-[var(--surface-app)]">
      {/* The search frames draw the wordmark and avatar only: this page is the
          search, so the phone header's search icon would lead back to itself. */}
      <SiteHeader user={user} showSearch={false} />
      {/* `flex flex-col` so the empty state below can claim the leftover height.
          Without it a no-results page leaves a tall blank band and the footer
          reads as having "ridden up" into the middle of the screen (BUG-005). */}
      {/* 52rem, not the 72rem the browsing pages use. A results list is read,
          not scanned by picture: at full width the title sat hard left and its
          thumbnail was stranded ~600px away at the right edge, and nothing tied
          the two together. Narrowing the column is what stops this reading as a
          phone layout stretched to fill a monitor.
          Phone: the frames' 16px gutter, and rows that run edge to edge. */}
      {/* WEBSITE (`lg` and up): the browsing rails, so the filters and the rest
          of the site sit beside the results instead of behind a sheet — the
          same frame /feed, /questions and /requests use. The phone keeps the
          frame's own gutter and rhythm. */}
      <main className="flex flex-1 flex-col">
        <BrowseLayout
          current="reviews"
          outerClassName="mx-auto flex w-full max-w-[52rem] flex-1 flex-col px-4 pb-8 pt-3 md:px-6 md:py-8 lg:max-w-[76rem] lg:px-10 lg:py-10"
          contentClassName="flex flex-1 flex-col"
          aside={
            activeTab === "people" ? (
              // People has nothing to refine; review filters here would do
              // nothing for the list beside them.
              <TakePartGroup />
            ) : activeTab === "sellers" ? (
              // MQA-035: the Sellers tab's own order and filters - the same
              // URLs its Sort and All filters sheets write. The review
              // controls this rail used to show here took the reader off the
              // tab to the review feed.
              <>
                <RailGroup title="Refine">
                  <RailChoices
                    current={state.sellerSort}
                    options={SELLER_SORTS.map((value) => [value, SELLER_SORT_LABEL[value]] as const)}
                    href={(sellerSort) => searchTabHref("sellers", { ...state, sellerSort })}
                  />
                </RailGroup>
                <h2 className={`${RAIL_LABEL} mt-8`}>Marketplace</h2>
                <RailChoices
                  current={state.platform}
                  options={[
                    [undefined, "All marketplaces"],
                    ["shopee", "Shopee"],
                    ["lazada", "Lazada"],
                  ]}
                  href={(platform) => searchTabHref("sellers", { ...state, platform })}
                />
                <h2 className={`${RAIL_LABEL} mt-8`}>Profile</h2>
                <RailChoices
                  current={state.claimed === true ? "claimed" : state.claimed === false ? "unclaimed" : undefined}
                  options={[
                    [undefined, "All stores"],
                    ["claimed", "Claimed profiles only"],
                    ["unclaimed", "Unclaimed profiles only"],
                  ]}
                  href={(v) =>
                    searchTabHref("sellers", { ...state, claimed: v === "claimed" ? true : v === "unclaimed" ? false : undefined })
                  }
                />
                <h2 className={`${RAIL_LABEL} mt-8`}>Rating</h2>
                <RailChoices
                  current={state.minRating}
                  options={[
                    [undefined, "Any"],
                    [4, "4★ & up"],
                    [3, "3★ & up"],
                  ]}
                  href={(minRating) => searchTabHref("sellers", { ...state, minRating })}
                />
                <h2 className={`${RAIL_LABEL} mt-8`}>Answers buyers</h2>
                <RailChoices
                  current={state.answers}
                  options={[
                    [undefined, "Any time"],
                    ["day", ANSWER_WINDOW_LABEL.day],
                    ["week", ANSWER_WINDOW_LABEL.week],
                  ]}
                  href={(answers) => searchTabHref("sellers", { ...state, answers })}
                />
                <TakePartGroup className="mt-8" />
              </>
            ) : activeTab === "questions" ? (
              // MQA-035: the Questions tab's own order and time.
              <>
                <RailGroup title="Refine">
                  <RailChoices
                    current={state.questionSort}
                    options={[
                      ["newest", "Latest"],
                      ["oldest", "Oldest"],
                    ]}
                    href={(questionSort) => searchTabHref("questions", { ...state, questionSort })}
                  />
                </RailGroup>
                <h2 className={`${RAIL_LABEL} mt-8`}>Time</h2>
                <RailChoices
                  current={period}
                  options={[
                    ["all", "All time"],
                    ["year", "Past year"],
                    ["month", "Past month"],
                  ]}
                  href={(value) => searchTabHref("questions", { ...state, period: value })}
                />
                <TakePartGroup className="mt-8" />
              </>
            ) : (
            <>
              <RailGroup title="Refine">
                <ul className="mt-3 flex flex-col gap-2 text-[13px]">
                  {(
                    [
                      ["wilson", "Most helpful"],
                      ["newest", "Latest"],
                      ["oldest", "Oldest"],
                      ["lowest", "Lowest rated"],
                    ] as const
                  ).map(([value, label]) => (
                    <li key={value}>
                      <Link
                        href={searchTabHref("reviews", { ...state, sort: value })}
                        aria-current={sort === value ? "true" : undefined}
                        className={sort === value ? "font-semibold text-[var(--accent-primary)]" : RAIL_ACTION}
                      >
                        {label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </RailGroup>

              <h2 className={`${RAIL_LABEL} mt-8`}>Time</h2>
              <ul className="mt-3 flex flex-col gap-2 text-[13px]">
                {(
                  [
                    ["all", "All time"],
                    ["year", "Past year"],
                    ["month", "Past month"],
                  ] as const
                ).map(([value, label]) => (
                  <li key={value}>
                    <Link
                      href={searchTabHref("reviews", { ...state, period: value })}
                      aria-current={period === value ? "true" : undefined}
                      className={period === value ? "font-semibold text-[var(--accent-primary)]" : RAIL_ACTION}
                    >
                      {label}
                    </Link>
                  </li>
                ))}
              </ul>

              {/* The sheet's Rating, Show only and Variant (Figma 7762:9999), as
                  links: each toggles its own choice, the same URLs the sheet writes. */}
              <h2 className={`${RAIL_LABEL} mt-8`}>Rating</h2>
              <RailToggles
                items={STAR_GROUPS.map((n) => ({
                  label: `${n} ★`,
                  on: Boolean(state.stars?.includes(n)),
                  href: searchTabHref("reviews", {
                    ...state,
                    stars: state.stars?.includes(n) ? state.stars.filter((x) => x !== n) : [...(state.stars ?? []), n],
                  }),
                }))}
              />
              <h2 className={`${RAIL_LABEL} mt-8`}>Show only</h2>
              <RailToggles
                items={(
                  [
                    ["photos", "With photos"],
                    ["verified", "Verified buyers"],
                    ["recommends", "Recommends it"],
                  ] as const
                ).map(([key, label]) => ({
                  label,
                  on: Boolean(state[key]),
                  href: searchTabHref("reviews", { ...state, [key]: !state[key] }),
                }))}
              />
              {variants.length ? (
                <>
                  <h2 className={`${RAIL_LABEL} mt-8`}>Variant</h2>
                  <RailChoices
                    current={state.variant}
                    options={[[undefined, "All"], ...variants.map((v) => [v, v] as const)]}
                    href={(variant) => searchTabHref("reviews", { ...state, variant })}
                  />
                </>
              ) : null}

              {/* QA-053: the sheet's Review score, Trust rating and Budget, as
                  links, the same URLs the phone's sheet writes. */}
              <h2 className={`${RAIL_LABEL} mt-8`}>Review score</h2>
              <RailChoices
                current={state.lens}
                options={[
                  [undefined, "Any"],
                  ["hidden_gems", LENS_LABEL.hidden_gems],
                  ["controversial", LENS_LABEL.controversial],
                  ["trending", LENS_LABEL.trending],
                ]}
                href={(lens) => searchTabHref("reviews", { ...state, lens })}
              />

              <h2 className={`${RAIL_LABEL} mt-8`}>Trust rating</h2>
              <RailChoices
                current={state.trust}
                options={[
                  [undefined, "All"],
                  ["low", "0–79"],
                  ["high", "80–100"],
                ]}
                href={(trust) => searchTabHref("reviews", { ...state, trust })}
              />

              <h2 className={`${RAIL_LABEL} mt-8`}>Budget</h2>
              <RailChoices
                current={state.maxPrice}
                options={[[undefined, "Any price"], ...BUDGET_STEPS.map((n) => [n, budgetLabel(n)] as const)]}
                href={(maxPrice) => searchTabHref("reviews", { ...state, maxPrice })}
              />

              {/* QA-025: several categories at once. Each link adds or removes
                  its category from the set; "All" clears the set. */}
              <h2 className={`${RAIL_LABEL} mt-8`}>Category</h2>
              <ul className="mt-3 flex flex-wrap gap-2">
                <li>
                  <Link
                    href={searchTabHref("reviews", { ...state, categories: [] })}
                    className={`inline-block rounded-[var(--radius-pill)] px-3 py-1.5 text-[13px] shadow-[var(--shadow-hairline-inset)] ${
                      categories.length
                        ? "text-[var(--text-secondary)] hover:text-[var(--accent-primary)]"
                        : "font-semibold text-[var(--accent-primary)]"
                    }`}
                  >
                    All
                  </Link>
                </li>
                {RAIL_CATEGORIES.map((c) => {
                  const on = categories.includes(c.slug);
                  return (
                    <li key={c.slug}>
                      <Link
                        href={searchTabHref("reviews", { ...state, categories: toggleCategory(categories, c.slug) })}
                        aria-pressed={on}
                        className={`inline-block rounded-[var(--radius-pill)] px-3 py-1.5 text-[13px] shadow-[var(--shadow-hairline-inset)] ${
                          on
                            ? "font-semibold text-[var(--accent-primary)]"
                            : "text-[var(--text-secondary)] hover:text-[var(--accent-primary)]"
                        }`}
                      >
                        {c.label}
                      </Link>
                    </li>
                  );
                })}
              </ul>

              <TakePartGroup className="mt-8" />
            </>
            )
          }
        >
          {fromCategories ? (
            <Link
              href="/categories"
              className="mb-5 inline-flex items-center gap-1 text-[13px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              <CaretLeft size={16} /> All categories
            </Link>
          ) : null}

          {/* The frames' SearchBar: 56px at radius 32 with a #323232 hairline, a
            28px magnifier 16px in, the query in 16px Poppins at 0.8px tracking
            56px in, and a 28px clear glyph 16px from the right edge. Those are
            the PHONE's numbers and they stay the phone's numbers.

            BUG-034, from `md` up. QA: "the search bar is taller than needed and
            its width doesn't match the content below it." Both were true, and
            both came from carrying the mobile frame's proportions onto a
            desktop page. A 56px field is right at 390 where it is the screen's
            primary control; at 1440 it sat above a grid of cards it did not
            line up with, capped at 40rem inside a much wider column, reading as
            a blown-up phone control rather than a page element.

            So: the frame's 56px on phones, the design system's 48px input
            height (`--control-input-h`) from `md`, and the cap dropped so the
            field spans the same content column as the pills and the cards
            underneath it. The horizontal insets are left alone: the magnifier
            and the clear control are absolutely positioned and vertically
            centred, so they follow the height on their own, and narrowing the
            gutters would only push the text under the clear button. */}
          <div className="max-w-[40rem] md:max-w-none">
            <RememberSearch q={q} />
            <SearchAutocomplete
              defaultValue={q}
              placeholder="Search products, reviews, or ask a question"
              showClear
              tone="strong"
              recents
              inputClassName={`h-14 w-full rounded-[32px] border border-[var(--base-gray-600)] bg-[var(--surface-app)] pl-[56px] pr-[52px] text-[16px] tracking-[0.8px] text-[var(--text-primary)] outline-none placeholder:text-[var(--text-muted)] md:h-[var(--control-input-h)] md:text-[15px] ${SEARCH_FOCUS}`}
            />
          </div>

          <SearchTabs active={activeTab} state={state} />

          {/* All filters / Sort, on every tab, as all three search frames draw
            them (3481:1776, 3481:1894, 3954:650). Each sheet offers only what
            that tab's API serves (SearchFilterBar). On reviews the pills are
            the phone's control: from `lg` the rail carries the same order,
            time and categories, so drawing both would be two controls for one
            choice. The rail has nothing for questions or stores, so their
            pills stay at every width. */}
          {chosen && resolution ? (
            <div className="-mx-4 mt-4 md:mx-0">
              <SearchProductBar
                mode={activeTab === "questions" ? "questions" : "reviews"}
                chosen={chosen}
                matches={resolution.matches}
                query={q}
                baseQuery={baseQuery}
                now={renderedAt}
              />
            </div>
          ) : null}

          {/* People has nothing to filter or sort: the closest names come first. */}
          {activeTab === "people" ? null : (
            <div className={activeTab === "reviews" ? "lg:hidden" : undefined}>
              <SearchFilterBar
                tab={activeTab}
                state={state}
                // With a product chosen the phone frame draws ListHeader/Reviews:
                // the count beside "Most helpful" and "Filters" (7702:7593).
                count={reviewHeader}
                productId={reviewProduct}
                variants={variants}
              />
            </div>
          )}

          {/* The phone frames go straight from the tabs to the results, so the
            heading is kept for screen readers and hidden below `md`. */}
          <h1 className="mt-8 text-[20px] font-bold text-[var(--text-primary)] max-md:sr-only">{heading}</h1>

          {activeTab === "people" ? (
            people === null ? (
              <Unavailable what="people" />
            ) : people.length > 0 ? (
              <ul className="-mx-4 md:mx-0 md:mt-3 md:border-t md:border-[var(--line-hairline-10)]">
                {people.map((person) => (
                  <PersonResultRow key={person.id} person={person} />
                ))}
              </ul>
            ) : (
              <EmptyResults
                icon={<UsersThree size={40} className="text-[var(--text-muted)]" />}
                title={q.trim() ? "No one by that name" : "Find a member"}
                body={
                  q.trim()
                    ? "Try their @handle or the name on their profile."
                    : "Type a name or @handle to find someone and open their profile."
                }
              />
            )
          ) : activeTab === "sellers" ? (
            sellers === null ? (
              <Unavailable what="sellers" />
            ) : sellers.length > 0 ? (
              <ul className="-mx-4 md:mx-0 md:mt-3 md:border-t md:border-[var(--line-hairline-10)]">
                {sellers.map((seller) => (
                  <SellerResultRow key={seller.id} seller={seller} />
                ))}
              </ul>
            ) : (
              <EmptyResults
                icon={<Storefront size={40} className="text-[var(--text-muted)]" />}
                title={searching ? "No sellers found" : "No sellers yet"}
                body={
                  searching
                    ? "Try the store name as the marketplace shows it."
                    : "Stores appear here once a buyer rates one."
                }
              />
            )
          ) : activeTab === "questions" && chosen && questionTerms && questions !== null ? (
            <div className="-mx-4 md:mx-0">
              <QuestionMatch
                productName={chosen.product.line || chosen.product.canonical_name || "this product"}
                terms={questionTerms}
                matches={questions}
                best={bestMatch}
                related={related}
                total={chosen.card?.questions ?? 0}
                activeNow={chosen.card?.active_now ?? 0}
                seeAllHref={`/search?${new URLSearchParams({ q: resolution?.productTerms ?? q, tab: "questions", product: chosen.product.id })}`}
                now={renderedAt}
              />
            </div>
          ) : activeTab === "questions" ? (
            <>
            {questions === null ? (
              <Unavailable what="questions" />
            ) : questions.length > 0 ? (
              <ul className="mt-4 flex flex-col gap-3 md:mt-3">
                {questions.map((question) => (
                  <QuestionResultRow key={question.id} question={question} />
                ))}
              </ul>
            ) : (
              <EmptyResults
                icon={<ChatCircle size={40} className="text-[var(--text-muted)]" />}
                title={searching ? "No questions found" : "Ask about a product"}
                body={
                  searching
                    ? "Try a different product name or wording."
                    : "Search for a product to see what buyers are asking about it."
                }
              />
            )}
            {requests.length > 0 ? (
              <section aria-label="Review requests" data-testid="search-requests" className="mt-6 px-4 md:px-0">
                <h2 className="text-[14px] font-semibold text-[var(--text-primary)]">Review requests</h2>
                <ul className="mt-2 flex flex-col gap-2">
                  {requests.map((r) => (
                    <li key={r.id}>
                      <Link
                        href={`/requests/${r.id}`}
                        className="block rounded-[var(--radius-sm)] bg-[var(--surface-card)] px-4 py-3 shadow-[var(--shadow-hairline-inset)] hover:underline"
                      >
                        <span className="block text-[14px] font-medium text-[var(--text-primary)]">{r.title}</span>
                        <span className="block text-[12px] text-[var(--text-secondary)]">
                          {[
                            r.product_name,
                            r.status === "fulfilled"
                              ? "Answered: Best Answer picked"
                              : r.status === "open"
                                ? `Open · ${r.answer_count ?? 0} ${(r.answer_count ?? 0) === 1 ? "answer" : "answers"}`
                                : r.status,
                          ]
                            .filter(Boolean)
                            .join(" \u00b7 ")}
                        </span>
                      </Link>
                    </li>
                  ))}
                </ul>
              </section>
            ) : null}
            </>
          ) : results === null ? (
            <Unavailable what="reviews" />
          ) : results.length > 0 ? (
            <>
            {reviewTotal !== null ? (
              <p data-testid={reviewHeader !== null ? undefined : "review-total"} className={`mt-2 text-[13px] text-[var(--text-secondary)] ${reviewHeader !== null ? "max-lg:hidden" : ""}`}>
                {countLine(reviewTotal, ["review", "reviews"], reviewsPage, reviewPages)}
              </p>
            ) : null}
            {/* Figma Screen/Search/Reviews (7693:7336, read live 2026-10-05):
                each result is a ReviewQuoteCard (7702:7587) — the Author row,
                the title in quotes, up to four of the reviewer's own photos
                (+N) and the reactions — white at radius 16, 12px apart. The
                reactions stay live (QA-027/028): Helpful / Not helpful, the
                comments link and Share, drawn as the frame's 16px glyph and
                12px Light count. INTENTIONAL PRODUCT DIFFERENCE: the frame
                shows up-votes and comments only; the down-vote and Share are
                QA-027 requirements. NO PHOTO = NO DEFAULT PHOTO: a review
                without uploads is the card's Photos=No variant. */}
            <ul className="mt-3 flex flex-col gap-3">
              {results.map((r) => (
                <li key={r.id}>
                  <ReviewQuoteCard
                    bleed={false}
                    titleAs="h2"
                    href={`/reviews/${r.id}`}
                    username={r.username ?? r.author}
                    avatarUrl={r.avatarUrl ?? null}
                    age={r.ageLabel}
                    levelName={r.trustLevel ?? null}
                    stage={r.trustStage ?? null}
                    score={r.trustScore ?? null}
                    title={splitHeadline(r.title, r.product).rest || r.title}
                    subject={chosen ? null : (r.product ?? null)}
                    photos={r.photoUrls ?? []}
                    footer={
                      <div className="flex flex-wrap items-center gap-4" data-testid="row-engagement">
                        <ReviewVoteBar
                          variant="reactions"
                          reviewId={r.id}
                          helpful={r.helpfulCount ?? 0}
                          unhelpful={r.unhelpfulCount ?? 0}
                          canVote={Boolean(me)}
                          readOnly={Boolean(me) && (Boolean(me?.is_claimed_seller) || me?.id === r.authorId)}
                          myVote={r.myVote ?? null}
                        />
                        <Link
                          href={`/reviews/${r.id}#comments`}
                          className="inline-flex items-center gap-1 rounded-[8px] text-[12px] font-light leading-normal text-[var(--text-primary)] no-underline hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]"
                        >
                          <ChatCircle size={16} aria-hidden="true" />
                          {r.comments}
                          <span className="sr-only"> comments</span>
                        </Link>
                        <ShareButton title={r.title} reviewId={r.id} excerpt={r.excerpt ?? undefined} variant="inline" />
                      </div>
                    }
                  />
                </li>
              ))}
            </ul>
            {reviewTotal !== null ? (
              <PageNumbers page={reviewsPage} total={reviewTotal} size={REVIEWS_PER_PAGE} href={reviewPageHref} label="Review pages" maxPages={REVIEW_PAGES_MAX} />
            ) : null}
            </>
          ) : reviewsPage > 1 ? (
            <EmptyResults
              icon={<MagnifyingGlass size={40} className="text-[var(--text-muted)]" />}
              title="No more reviews"
              body="This page is past the last one. Go back to the first page."
            />
          ) : (
            <EmptyResults
              icon={<MagnifyingGlass size={40} className="text-[var(--text-muted)]" />}
              title={searching ? "No reviews found" : "Find the product you bought"}
              body={
                searching
                  ? "Try a different product name, brand, or category."
                  : "No need for the exact model. Just type what you know."
              }
            />
          )}
        </BrowseLayout>
      </main>
      {/* Screen/Search 6852:641 draws QuickActions/Button. */}
      <QuickActions />
      <SiteFooter />
    </div>
  );
}

/** A one-of group in the desktop rail: each choice a link, the current one marked. */
/** Rail links that each switch one choice on or off (Rating, Show only). */
function RailToggles({ items }: { items: { label: string; on: boolean; href: string }[] }) {
  return (
    <ul className="mt-3 flex flex-wrap gap-2">
      {items.map((item) => (
        <li key={item.label}>
          <Link
            href={item.href}
            aria-pressed={item.on}
            className={`inline-block rounded-[var(--radius-pill)] px-3 py-1.5 text-[13px] shadow-[var(--shadow-hairline-inset)] ${
              item.on ? "font-semibold text-[var(--accent-primary)]" : "text-[var(--text-secondary)] hover:text-[var(--accent-primary)]"
            }`}
          >
            {item.label}
          </Link>
        </li>
      ))}
    </ul>
  );
}

function RailChoices<T extends string | number>({
  current,
  options,
  href,
}: {
  current: T | undefined;
  options: readonly (readonly [T | undefined, string])[];
  href: (value: T | undefined) => string;
}) {
  return (
    <ul className="mt-3 flex flex-col gap-2 text-[13px]">
      {options.map(([value, label]) => {
        const on = value === current;
        return (
          <li key={label}>
            <Link
              href={href(value)}
              aria-current={on ? "true" : undefined}
              className={on ? "font-semibold text-[var(--accent-primary)]" : RAIL_ACTION}
            >
              {label}
            </Link>
          </li>
        );
      })}
    </ul>
  );
}

/**
 * The shared empty state for both tabs — one component so "no reviews" and "no
 * questions" cannot drift apart in spacing or voice.
 */
function EmptyResults({ icon, title, body }: { icon: React.ReactNode; title: string; body: string }) {
  return (
    <div className="flex flex-1 flex-col items-center justify-center py-16 text-center">
      {icon}
      <p className="mt-4 text-[16px] font-semibold text-[var(--text-primary)]">{title}</p>
      <p className="mt-1 max-w-[22rem] text-[14px] text-[var(--text-secondary)]">{body}</p>
    </div>
  );
}
