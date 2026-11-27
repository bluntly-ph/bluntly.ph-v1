"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  ArrowsDownUp,
  ChatCircleDots,
  CheckCircle,
  Hourglass,
  Image as ImageIcon,
  SealCheck,
  ShieldCheck,
  Sliders,
  Sparkle,
  Star,
  Storefront,
  Tag,
  ThumbsUp,
  Wallet,
} from "@phosphor-icons/react";

import { CATEGORIES } from "@/lib/landing-data";
import { feedQuery, sellerFilterParams } from "@/lib/search-filter-params";

import { Chip, ChipGroup, ChipSheet, StoreChip } from "./ChipSheet";
import { SortMenu, type SortOption } from "./SortMenu";

import {
  ANSWER_WINDOW_LABEL,
  BUDGET_STEPS,
  budgetLabel,
  clearCategoryHref,
  DEFAULT_SELLER_SORT,
  LENS_INFO,
  LENS_LABEL,
  PERIOD_LABEL,
  searchTabHref,
  SELLER_SORT_INFO,
  SELLER_SORT_LABEL,
  STAR_GROUPS,
  TRUST_LABEL,
  type AnswerWindow,
  type Period,
  type QuestionSort,
  type ReviewLens,
  type ReviewSort,
  type SearchState,
  type SearchTab,
  type SellerPlatformFilter,
  type SellerRatingFloor,
  type SellerSort,
  type TrustBand,
} from "./search-tabs-model";

/**
 * The "All filters" and "Sort" pills under the result tabs, and what they
 * open. Figma, re-read 2026-10-07 (flow map 7763:9173): the sort pill opens
 * the dropdown Menu (Screen/Search/Reviews/Sort open 7762:9948, SortMenu.tsx);
 * the filter pill opens the FilterChip sheet (Screen/Search/Reviews/Filters
 * 7762:9999; Sheet/Filter sellers 8462:36591; ChipSheet.tsx). They replace the
 * radio sheets "All filters" (1587:4658) and "Sort" (1591:5408), which the
 * file has retired for search.
 *
 * Pills: 32px tall, 12px sides, a 16px glyph 4px before 12px Poppins Regular,
 * radius 16, a 1px ink outline — the brand outline and text once the reader
 * has applied one. 12px apart, 12px under the tab rule. Each applied filter
 * follows a 26px hairline as a filled brand chip, as the frame draws
 * "80 - 100" and "All time"; tapping one reopens the sheet.
 *
 * Sort applies on the tap, as the menu draws no button. Filters commit on the
 * sheet's pill ("Show reviews"), so a reader can change their mind mid-sheet
 * without the results reloading underneath them.
 *
 * WHAT EACH TAB OFFERS — only what its API does, because a control that
 * changes nothing is a dead control:
 *  - Reviews. Filters, in the frame's order: Rating (All / 5★-1★, several at
 *    once), Show only (With photos / Verified buyers / Recommends it), Variant
 *    (with one product chosen, when its reviewers named any); then ours:
 *    Review score (Hidden Gems / Controversial / Trending), Trust rating,
 *    Budget, Time, and Category, several at once (QA-025).
 *    Sort: Most helpful / Newest / Oldest / Lowest rated.
 *  - Questions. Filters: Time. Sort: Newest / Oldest.
 *  - Sellers. Filter sellers: Profile (claimed by the owner / unclaimed), Sells
 *    on, Rating (4★ & up / 3★ & up / Any) and Answers buyers (within a day /
 *    within a week). Sort: best evidenced (the default, MQA-033), the
 *    most-reviewed first, or name.
 *
 * The sheet's pill counts as the reader chooses ("Show 42 reviews", "Show 24
 * sellers"): GET /reviews/feed/count or /sellers/count through /api/bff, with
 * the same query builder the list uses (lib/search-filter-params). Questions
 * has no count endpoint, so its pill stays "Show questions". Step 2 of the
 * owner's "both, in two steps" (2026-10-07).
 *
 * The Review score lenses, Trust rating and Budget were left out until they
 * had definitions; they are written down in the backend's review_lenses.py
 * (QA-053, owner 2026-09-28) and said in each section's info. NOT OFFERED:
 * the Sort frame's "Reviewer credibility", which would rank people rather than
 * filter reviews by a band.
 */

type SheetKind = "filters" | "sort";

const REVIEW_SORTS: SortOption<ReviewSort>[] = [
  { value: "wilson", label: "Most helpful" },
  { value: "newest", label: "Newest" },
  { value: "oldest", label: "Oldest" },
  { value: "lowest", label: "Lowest rated" },
];

const QUESTION_SORTS: SortOption<QuestionSort>[] = [
  { value: "newest", label: "Newest" },
  { value: "oldest", label: "Oldest" },
];

const FILTER_CATEGORIES = CATEGORIES.filter((c) => c.slug !== "trending");

const PERIODS: { value: Period; label: string }[] = [
  { value: "all", label: "All time" },
  { value: "year", label: PERIOD_LABEL.year },
  { value: "month", label: PERIOD_LABEL.month },
];

const LENSES: { value: "" | ReviewLens; label: string }[] = [
  { value: "", label: "All" },
  { value: "hidden_gems", label: LENS_LABEL.hidden_gems },
  { value: "controversial", label: LENS_LABEL.controversial },
  { value: "trending", label: LENS_LABEL.trending },
];

const TRUSTS: { value: "" | TrustBand; label: string }[] = [
  { value: "", label: "All" },
  { value: "low", label: "0–79" },
  { value: "high", label: "80–100" },
];


const PLATFORMS: { value: SellerPlatformFilter; label: string }[] = [
  { value: "shopee", label: "Shopee" },
  { value: "lazada", label: "Lazada" },
];

const SELLER_SORTS: SellerSort[] = ["ranked", "reviews", "name"];

const SHOW_ONLY = [
  { key: "photos", label: "With photos" },
  { key: "verified", label: "Verified buyers" },
  { key: "recommends", label: "Recommends it" },
] as const;
type ShowOnlyKey = (typeof SHOW_ONLY)[number]["key"];

const SELLER_RATINGS: { value: SellerRatingFloor | undefined; label: string }[] = [
  { value: 4, label: "4★ & up" },
  { value: 3, label: "3★ & up" },
  { value: undefined, label: "Any" },
];

const ANSWER_WINDOWS: AnswerWindow[] = ["day", "week"];

/**
 * The sheet pill's live count: asks `path` (a count endpoint behind /api/bff)
 * a quarter-second after the choices settle, and forgets an answer that a
 * newer choice has overtaken. Null while unknown, so the pill keeps its words.
 */
function useLiveCount(path: string | null): number | null {
  const [answer, setAnswer] = useState<{ path: string; total: number } | null>(null);
  useEffect(() => {
    if (!path) return;
    const ctrl = new AbortController();
    const timer = setTimeout(() => {
      fetch(`/api/bff/api/v1/${path}`, { signal: ctrl.signal })
        .then((r) => (r.ok ? r.json() : null))
        .then((body: { total?: number } | null) => {
          if (typeof body?.total === "number") setAnswer({ path, total: body.total });
        })
        .catch(() => {});
    }, 250);
    return () => {
      clearTimeout(timer);
      ctrl.abort();
    };
  }, [path]);
  return path && answer?.path === path ? answer.total : null;
}

const FOCUS =
  "focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--accent-primary)]";

// 11px sides: Figma strokes inside the frame, so its 12px padding includes the
// 1px outline ("Sort" measures 68px there).
const PILL =
  "inline-flex h-8 shrink-0 cursor-pointer items-center gap-1 whitespace-nowrap rounded-[var(--radius-md)] px-[11px] text-[12px] leading-none";

const NOUN: Record<SearchTab, string> = {
  reviews: "Reviews",
  questions: "Questions",
  sellers: "Sellers",
  people: "People",
};

export function SearchFilterBar({
  tab,
  state,
  count = null,
  productId = null,
  variants = [],
}: {
  tab: SearchTab;
  state: SearchState;
  /**
   * Reviews with a product chosen: Figma "ListHeader/Reviews" (7702:7593 in
   * Screen/Search/Reviews 7693:7336) — the count in 16px Medium at the left,
   * the sort chip (named for the current order, "Most helpful") and "Filters"
   * at the right, 8px apart. Null keeps the "All filters" / "Sort" pills.
   */
  count?: string | null;
  /** Reviews narrowed to one product (the product bar's Switch). */
  productId?: string | null;
  /** That product's reported variants, for the Variant chips. */
  variants?: readonly string[];
}) {
  const router = useRouter();
  const [sheet, setSheet] = useState<SheetKind | null>(null);
  const trigger = useRef<HTMLButtonElement | null>(null);
  const bar = useRef<HTMLDivElement | null>(null);
  // Where the sort menu hangs: the pill that opened it, and the bar it sits in.
  const [menuAnchor, setMenuAnchor] = useState<{ pill: HTMLElement; bar: HTMLElement | null } | null>(null);

  const categories = state.categories ?? [];
  const period = state.period ?? "all";
  const sort = state.sort ?? "wilson";
  const questionSort = state.questionSort ?? "newest";
  const sellerSort = state.sellerSort ?? DEFAULT_SELLER_SORT;

  const [draftCategories, setDraftCategories] = useState<string[]>([]);
  const [draftPeriod, setDraftPeriod] = useState<Period>("all");
  const [draftLens, setDraftLens] = useState<"" | ReviewLens>("");
  const [draftTrust, setDraftTrust] = useState<"" | TrustBand>("");
  const [draftBudget, setDraftBudget] = useState<number | undefined>(undefined);
  const [draftPlatform, setDraftPlatform] = useState<"" | SellerPlatformFilter>("");
  const [draftStars, setDraftStars] = useState<number[]>([]);
  const [draftShow, setDraftShow] = useState<Record<ShowOnlyKey, boolean>>({ photos: false, verified: false, recommends: false });
  const [draftVariant, setDraftVariant] = useState<string | undefined>(undefined);
  const [draftClaimed, setDraftClaimed] = useState<boolean | undefined>(undefined);
  const [draftMinRating, setDraftMinRating] = useState<SellerRatingFloor | undefined>(undefined);
  const [draftAnswers, setDraftAnswers] = useState<AnswerWindow | undefined>(undefined);

  const open = (kind: SheetKind, from: HTMLButtonElement) => {
    trigger.current = from;
    setMenuAnchor(kind === "sort" ? { pill: from, bar: count !== null ? bar.current : null } : null);
    // Every opening starts from what is applied, so a cancelled change is gone.
    setDraftCategories([...categories]);
    setDraftPeriod(period);
    setDraftLens(state.lens ?? "");
    setDraftTrust(state.trust ?? "");
    setDraftBudget(state.maxPrice);
    setDraftPlatform(state.platform ?? "");
    setDraftStars([...(state.stars ?? [])]);
    setDraftShow({ photos: Boolean(state.photos), verified: Boolean(state.verified), recommends: Boolean(state.recommends) });
    setDraftVariant(state.variant);
    setDraftClaimed(state.claimed);
    setDraftMinRating(state.minRating);
    setDraftAnswers(state.answers);
    setSheet(kind);
  };

  // Stable, so the sheet's key and scroll-lock effect runs once per opening.
  const close = useCallback(() => {
    setSheet(null);
    trigger.current?.focus();
  }, []);

  const go = (next: SearchState) => {
    setSheet(null);
    router.push(searchTabHref(tab, next));
  };

  const base: SearchState = { q: state.q, from: state.from };
  const applied: { key: string; label: string; icon?: React.ReactNode }[] = [];
  if (tab === "reviews") {
    for (const slug of categories) {
      const c = FILTER_CATEGORIES.find((x) => x.slug === slug);
      if (c) applied.push({ key: `c-${slug}`, label: c.label, icon: <c.icon size={16} aria-hidden="true" /> });
    }
    if (state.lens) {
      applied.push({ key: "lens", label: LENS_LABEL[state.lens], icon: <Sparkle size={16} aria-hidden="true" /> });
    }
    if (state.trust) {
      applied.push({ key: "trust", label: TRUST_LABEL[state.trust], icon: <ShieldCheck size={16} aria-hidden="true" /> });
    }
    if (state.maxPrice) {
      applied.push({ key: "budget", label: budgetLabel(state.maxPrice), icon: <Wallet size={16} aria-hidden="true" /> });
    }
    if (state.stars?.length) {
      applied.push({ key: "stars", label: state.stars.map((n) => `${n}★`).join(", "), icon: <Star size={16} aria-hidden="true" /> });
    }
    if (state.photos) applied.push({ key: "photos", label: "With photos", icon: <ImageIcon size={16} aria-hidden="true" /> });
    if (state.verified) applied.push({ key: "verified", label: "Verified buyers", icon: <SealCheck size={16} aria-hidden="true" /> });
    if (state.recommends) applied.push({ key: "recommends", label: "Recommends it", icon: <ThumbsUp size={16} aria-hidden="true" /> });
    if (state.variant && productId) applied.push({ key: "variant", label: state.variant, icon: <Tag size={16} aria-hidden="true" /> });
  }
  if (tab !== "sellers" && period !== "all") {
    applied.push({ key: "period", label: PERIOD_LABEL[period], icon: <Hourglass size={16} aria-hidden="true" /> });
  }
  if (tab === "sellers" && state.platform) {
    applied.push({
      key: "platform",
      label: PLATFORMS.find((p) => p.value === state.platform)?.label ?? state.platform,
      icon: <Storefront size={16} aria-hidden="true" />,
    });
  }
  if (tab === "sellers" && state.claimed !== undefined) {
    applied.push({ key: "claimed", label: state.claimed ? "Claimed" : "Unclaimed", icon: <CheckCircle size={16} aria-hidden="true" /> });
  }
  if (tab === "sellers" && state.minRating) {
    applied.push({ key: "rating", label: `${state.minRating}★ & up`, icon: <Star size={16} aria-hidden="true" /> });
  }
  if (tab === "sellers" && state.answers) {
    applied.push({ key: "answers", label: ANSWER_WINDOW_LABEL[state.answers], icon: <ChatCircleDots size={16} aria-hidden="true" /> });
  }

  const sorted =
    tab === "reviews" ? sort !== "wilson" : tab === "questions" ? questionSort !== "newest" : sellerSort !== DEFAULT_SELLER_SORT;

  // Chip/Action (7166:4933): Default a dark outline; Active (a filter or a
  // non-default order applied) the brand outline and text on the #fbede3 tint.
  const outline = (active: boolean) =>
    `${PILL} border ${
      active
        ? "border-[var(--accent-primary)] bg-[var(--status-high-bg)] text-[var(--accent-primary)]"
        : "border-[var(--text-primary)] text-[var(--text-primary)]"
    } ${FOCUS}`;

  // Reset clears the sheet's choices; the pill applies them (Figma "Reset"
  // sits in the sheet's header, beside the title).
  const resetFilters = () => {
    setDraftCategories([]);
    setDraftPeriod("all");
    setDraftLens("");
    setDraftTrust("");
    setDraftBudget(undefined);
    setDraftPlatform("");
    setDraftStars([]);
    setDraftShow({ photos: false, verified: false, recommends: false });
    setDraftVariant(undefined);
    setDraftClaimed(undefined);
    setDraftMinRating(undefined);
    setDraftAnswers(undefined);
  };

  // What the sheet would show, for the live count and for applying.
  const draftReviews: SearchState = {
    categories: draftCategories,
    period: draftPeriod,
    lens: draftLens || undefined,
    trust: draftTrust || undefined,
    maxPrice: draftBudget,
    stars: draftStars,
    ...draftShow,
    variant: productId ? draftVariant : undefined,
  };
  const draftSellers: SearchState = {
    platform: draftPlatform || undefined,
    claimed: draftClaimed,
    minRating: draftMinRating,
    answers: draftAnswers,
  };
  const livePath =
    sheet !== "filters"
      ? null
      : tab === "reviews"
        ? `reviews/feed/count?${feedQuery({
            ...draftReviews,
            q: productId ? undefined : state.q,
            product_id: productId ?? undefined,
          })}`
        : tab === "sellers"
          ? `sellers/count?${sellerFilterParams({ ...draftSellers, q: state.q })}`
          : null;
  const live = useLiveCount(livePath);
  const showLabel = (noun: string, one: string) =>
    live === null ? `Show ${noun}` : `Show ${live.toLocaleString("en-PH")} ${live === 1 ? one : noun}`;

  const applyFilters = () => {
    if (tab === "reviews") {
      const none =
        draftCategories.length === 0 && draftPeriod === "all" && !draftLens && !draftTrust && draftBudget === undefined &&
        draftStars.length === 0 && !draftShow.photos && !draftShow.verified && !draftShow.recommends && !draftReviews.variant;
      if (none) {
        // Everything cleared: BUG-011 — a visitor from /categories goes back there.
        setSheet(null);
        router.push(clearCategoryHref({ q: state.q, sort, from: state.from }));
        return;
      }
      go({ ...base, sort, ...draftReviews });
    }
    else if (tab === "questions") go({ ...base, questionSort, period: draftPeriod });
    else go({ ...base, sellerSort, ...draftSellers });
  };

  // The review filters a Sort change keeps.
  const reviewFilters: SearchState = {
    categories,
    period,
    lens: state.lens,
    trust: state.trust,
    maxPrice: state.maxPrice,
    stars: state.stars,
    photos: state.photos,
    verified: state.verified,
    recommends: state.recommends,
    variant: state.variant,
  };

  const chooseReviewSort = (next: ReviewSort) => go({ ...base, ...reviewFilters, sort: next });
  const chooseQuestionSort = (next: QuestionSort) => go({ ...base, period, questionSort: next });
  const chooseSellerSort = (next: SellerSort) =>
    go({ ...base, platform: state.platform, claimed: state.claimed, minRating: state.minRating, answers: state.answers, sellerSort: next });

  const sortLabel = REVIEW_SORTS.find((o) => o.value === sort)?.label ?? "Most helpful";

  const timeSection = (
    <ChipGroup label="Time" info="Shows only what was posted within the period you pick.">
      {PERIODS.map((p) => (
        <Chip key={p.value} label={p.label} selected={draftPeriod === p.value} onToggle={() => setDraftPeriod(p.value)} />
      ))}
    </ChipGroup>
  );

  return (
    <>
      {/* 2px of vertical padding, taken back out of the margins, so the focus
          ring is not clipped by the scroller while the pills stay on the
          frame's y — 12px under the tab rule. */}
      {count !== null ? (
        <div ref={bar} className="mt-4 flex min-h-10 items-center justify-between gap-2 pt-2">
          <p className="min-w-0 truncate text-[16px] font-medium leading-normal" data-testid="review-total">
            {count}
          </p>
          <div className="flex shrink-0 items-center gap-2">
            <button
              type="button"
              aria-haspopup="menu"
              aria-expanded={sheet === "sort"}
              onClick={(e) => open("sort", e.currentTarget)}
              className={outline(sorted)}
            >
              <ArrowsDownUp size={16} aria-hidden="true" />
              {sortLabel}
            </button>
            <button
              type="button"
              aria-haspopup="dialog"
              aria-expanded={sheet === "filters"}
              onClick={(e) => open("filters", e.currentTarget)}
              className={outline(applied.length > 0)}
            >
              <Sliders size={16} aria-hidden="true" className="rotate-90" />
              Filters
            </button>
          </div>
        </div>
      ) : null}
      <div className={count !== null && applied.length === 0 ? "hidden" : "-mx-4 -mb-0.5 mt-2.5 overflow-x-auto px-4 py-0.5 [scrollbar-width:none] md:mx-0 md:mt-[18px] md:px-0"}>
        <div className="flex w-max items-center gap-3">
          {count !== null ? null : (
          <>
          <button
            type="button"
            aria-haspopup="dialog"
            aria-expanded={sheet === "filters"}
            onClick={(e) => open("filters", e.currentTarget)}
            className={outline(applied.length > 0)}
          >
            <Sliders size={16} aria-hidden="true" className="rotate-90" />
            All filters
          </button>
          <button
            type="button"
            aria-haspopup="menu"
            aria-expanded={sheet === "sort"}
            onClick={(e) => open("sort", e.currentTarget)}
            className={outline(sorted)}
          >
            <ArrowsDownUp size={16} aria-hidden="true" />
            Sort
          </button>
          </>
          )}
          {applied.length > 0 ? (
            <>
              {count !== null ? null : <span aria-hidden="true" className="h-[26px] w-px shrink-0 bg-[var(--line-hairline-30)]" />}
              {applied.map((chip) => (
                <button
                  key={chip.key}
                  type="button"
                  aria-haspopup="dialog"
                  aria-label={`${chip.label}. Change filters`}
                  onClick={(e) => open("filters", e.currentTarget)}
                  className={`${PILL} bg-[var(--accent-primary)] text-[var(--text-on-brand)] ${FOCUS}`}
                >
                  {chip.icon}
                  {chip.label}
                </button>
              ))}
            </>
          ) : null}
        </div>
      </div>

      {sheet === "filters" ? (
        tab === "sellers" ? (
          <ChipSheet
            title="Filter sellers"
            tone="quiet"
            icon={<Sliders size={20} aria-hidden="true" className="shrink-0" />}
            submitLabel={showLabel("sellers", "seller")}
            onClose={close}
            onReset={resetFilters}
            onSubmit={applyFilters}
          >
            <ChipGroup label="Profile" tone="quiet" info="A claimed profile is run by the store itself, after it proved it owns it.">
              <Chip label="Claimed by the owner" selected={draftClaimed === true} onToggle={() => setDraftClaimed((v) => (v === true ? undefined : true))} />
              <Chip label="Unclaimed" selected={draftClaimed === false} onToggle={() => setDraftClaimed((v) => (v === false ? undefined : false))} />
            </ChipGroup>
            <ChipGroup label="Sells on" tone="quiet" info="Shows only stores on the marketplace you pick.">
              {PLATFORMS.map((p) => (
                <StoreChip
                  key={p.value}
                  store={p.value}
                  selected={draftPlatform === p.value}
                  onToggle={() => setDraftPlatform((v) => (v === p.value ? "" : p.value))}
                />
              ))}
            </ChipGroup>
            <ChipGroup label="Rating" tone="quiet" info="The store's overall rating from buyers, as its card shows it.">
              {SELLER_RATINGS.map((r) => (
                <Chip key={r.label} label={r.label} selected={draftMinRating === r.value} onToggle={() => setDraftMinRating(r.value)} />
              ))}
            </ChipGroup>
            <ChipGroup
              label="Answers buyers"
              tone="quiet"
              info="How long the store itself usually takes to answer a buyer's question: the middle of its answer times."
            >
              {ANSWER_WINDOWS.map((w) => (
                <Chip
                  key={w}
                  label={ANSWER_WINDOW_LABEL[w]}
                  selected={draftAnswers === w}
                  onToggle={() => setDraftAnswers((v) => (v === w ? undefined : w))}
                />
              ))}
            </ChipGroup>
          </ChipSheet>
        ) : (
          <ChipSheet
            title="Filters"
            submitLabel={tab === "reviews" ? showLabel("reviews", "review") : `Show ${NOUN[tab].toLowerCase()}`}
            onClose={close}
            onReset={resetFilters}
            onSubmit={applyFilters}
          >
            {tab === "reviews" ? (
              <>
                <ChipGroup label="Rating" info="The reviewer's stars. A 4.5-star review counts as 4★.">
                  <Chip label="All" selected={draftStars.length === 0} onToggle={() => setDraftStars([])} />
                  {STAR_GROUPS.map((n) => (
                    <Chip
                      key={n}
                      label={`${n} ★`}
                      selected={draftStars.includes(n)}
                      onToggle={() =>
                        setDraftStars((current) =>
                          current.includes(n) ? current.filter((x) => x !== n) : [...current, n].sort((a, b) => b - a),
                        )
                      }
                    />
                  ))}
                </ChipGroup>
                <ChipGroup
                  label="Show only"
                  info="With photos: the reviewer's own photos. Verified buyers: a proof of purchase was checked. Recommends it: the verdict is “Yes, absolutely”."
                >
                  {SHOW_ONLY.map((o) => (
                    <Chip
                      key={o.key}
                      label={o.label}
                      selected={draftShow[o.key]}
                      onToggle={() => setDraftShow((d) => ({ ...d, [o.key]: !d[o.key] }))}
                    />
                  ))}
                </ChipGroup>
                {productId && variants.length ? (
                  <ChipGroup label="Variant" info="The variant the reviewer said they bought.">
                    <Chip label="All" selected={draftVariant === undefined} onToggle={() => setDraftVariant(undefined)} />
                    {variants.map((v) => (
                      <Chip key={v} label={v} selected={draftVariant === v} onToggle={() => setDraftVariant((c) => (c === v ? undefined : v))} />
                    ))}
                  </ChipGroup>
                ) : null}
                <ChipGroup label="Review score" info={LENS_INFO}>
                  {LENSES.map((l) => (
                    <Chip key={l.value || "all"} label={l.label} selected={draftLens === l.value} onToggle={() => setDraftLens(l.value)} />
                  ))}
                </ChipGroup>
                <ChipGroup
                  label="Trust rating"
                  info="The reviewer's trust score, the 0–100 number beside their level on every review."
                >
                  {TRUSTS.map((t) => (
                    <Chip key={t.value || "all"} label={t.label} selected={draftTrust === t.value} onToggle={() => setDraftTrust(t.value)} />
                  ))}
                </ChipGroup>
                <ChipGroup
                  label="Budget"
                  info="What the reviewer says they paid. Reviews with no price paid are left out once you set a budget."
                >
                  <Chip label="Any price" selected={draftBudget === undefined} onToggle={() => setDraftBudget(undefined)} />
                  {BUDGET_STEPS.map((step) => (
                    <Chip key={step} label={budgetLabel(step)} selected={draftBudget === step} onToggle={() => setDraftBudget(step)} />
                  ))}
                </ChipGroup>
                {timeSection}
                <ChipGroup label="Category" info="Shows reviews of products in any of the categories you pick.">
                  <Chip label="All" selected={draftCategories.length === 0} onToggle={() => setDraftCategories([])} />
                  {FILTER_CATEGORIES.map((c) => (
                    <Chip
                      key={c.slug}
                      label={c.label}
                      selected={draftCategories.includes(c.slug)}
                      onToggle={() =>
                        setDraftCategories((current) =>
                          current.includes(c.slug) ? current.filter((x) => x !== c.slug) : [...current, c.slug],
                        )
                      }
                    />
                  ))}
                </ChipGroup>
              </>
            ) : (
              timeSection
            )}
          </ChipSheet>
        )
      ) : null}

      {sheet === "sort" && menuAnchor ? (
        tab === "reviews" ? (
          <SortMenu label="Sort reviews" anchor={menuAnchor.pill} bar={menuAnchor.bar} options={REVIEW_SORTS} value={sort} onChoose={chooseReviewSort} onClose={close} />
        ) : tab === "questions" ? (
          <SortMenu label="Sort questions" anchor={menuAnchor.pill} options={QUESTION_SORTS} value={questionSort} onChoose={chooseQuestionSort} onClose={close} />
        ) : (
          <SortMenu
            label="Sort sellers"
            anchor={menuAnchor.pill}
            options={SELLER_SORTS.map((value) => ({ value, label: SELLER_SORT_LABEL[value] }))}
            value={sellerSort}
            onChoose={chooseSellerSort}
            onClose={close}
            note={SELLER_SORT_INFO}
          />
        )
      ) : null}
    </>
  );
}

export default SearchFilterBar;
