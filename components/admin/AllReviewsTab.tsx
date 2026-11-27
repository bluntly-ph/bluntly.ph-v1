"use client";

import { ArrowsDownUp, Check, MagnifyingGlass, SlidersHorizontal } from "@phosphor-icons/react/dist/ssr";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import {
  EARN_LABELS,
  SORT_LABELS,
  STATE_LABELS,
  activeFilterCount,
  allReviewsHref,
  allReviewsQuery,
  postedText,
  queueStatusText,
  wilsonText,
  type AllReviewRow,
  type AllReviewsFilters,
  type AllReviewsPage,
  type AllReviewsResult,
  type AllReviewsSort,
  type AllReviewsState,
  type EarnState,
} from "@/components/admin/all-reviews-model";
import { EarningCell, RatingCell, earningPath, levelLabel } from "@/components/admin/queue/QueueCells";
import { Pagination } from "@/components/console/Pagination";
import { ProductThumbnail } from "@/components/console/ProductThumbnail";
import { ICON_BUTTON, MENU, usePopover } from "@/components/console/popover";
import { TOP_SEARCH_STATES } from "@/components/ui/search-styles";
import { MENU_ITEM } from "@/components/console/fields";

/**
 * All reviews (Figma Queue/AllReviews 8060:15564): the Reviews view with the
 * Queue switch off — every review that still exists, newest first.
 *
 * Rebuilt to the frame (owner, 2026-10-03): the toolbar's Sort / Filter /
 * Search menus replace the inline controls, and the table is Review (product
 * thumbnail, product, "by" author) / Level / Rating / Earnings / Wilson /
 * State / Posted, paged by the console Pagination (10 a page).
 *
 * What QA asked for before stays on every row without its own columns: the
 * row's tooltip (and its screen-reader text) gives the review's title, both
 * Wilson figures (public: every vote equal, 45-day decay; gate: trust-weighted,
 * what puts a review in the Review Queue), the votes, and why the review is or
 * is not in the queue. Wilson in the column is the public figure.
 *
 * The server filters, sorts and pages (`GET /admin/reviews`); nothing here
 * narrows the page it was given. Every control changes the URL.
 */
export function AllReviewsTab({
  result,
  filters,
  now,
}: {
  result: AllReviewsResult;
  filters: AllReviewsFilters;
  now: number;
}) {
  const page = result.available ? result.page : null;
  const items = page?.items ?? [];

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4" data-testid="all-reviews">
      <div className="overflow-x-auto rounded-[16px] border border-[var(--border-subtle)]">
        <table className="w-full min-w-[960px] border-collapse text-left text-[14px]">
          <caption className="sr-only">All reviews</caption>
          <thead className="bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
            <tr>
              {["Review", "Level", "Rating", "Earnings", "Wilson", "State", "Posted"].map((h) => (
                <th key={h} scope="col" className="h-10 px-3 font-normal">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {!result.available ? (
              <EmptyRow>
                <span role="alert">
                  {result.reason === "unauthenticated"
                    ? "Your session has ended. Sign in again to see the reviews."
                    : "The reviews could not be loaded. Nothing has changed; try again in a moment."}
                </span>
              </EmptyRow>
            ) : items.length === 0 ? (
              <EmptyRow>
                {filters.q || activeFilterCount(filters)
                  ? "No review matches these filters."
                  : "No reviews yet."}
              </EmptyRow>
            ) : (
              items.map((row) => <Row key={row.id} row={row} page={page!} now={now} />)
            )}
          </tbody>
        </table>
      </div>
      {page ? (
        <Pagination
          page={filters.page}
          size={filters.size}
          total={page.total}
          basePath="/admin/review-queue"
          query={allReviewsQuery(filters)}
          pageParam="apage"
          sizeParam="asize"
          label="All reviews pages"
        />
      ) : null}
    </div>
  );
}

function EmptyRow({ children }: { children: React.ReactNode }) {
  return (
    <tr>
      <td colSpan={7} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">
        {children}
      </td>
    </tr>
  );
}

const STATE_TONE: Record<AllReviewsState, string> = {
  published: "",
  taken_down: "",
  removed: "text-[var(--semantic-danger)]",
  deleted_by_author: "text-[var(--text-secondary)]",
};

function Row({ row, page, now }: { row: AllReviewRow; page: AllReviewsPage; now: number }) {
  const author = row.author?.display_name || (row.author?.username ? `@${row.author.username}` : "a removed account");
  const product = row.product.canonical_name ?? "Unnamed product";
  const rating = Number(row.star_rating);
  const down = row.state === "taken_down";
  const queue = queueStatusText(row, page);
  const detail =
    `${row.title} · Public Wilson ${wilsonText(row.wilson_score)}, gate Wilson ` +
    `${row.gate.wilson_lower_bound.toFixed(2)} · votes ${row.helpful_votes} up / ${row.unhelpful_votes} down · ${queue}`;
  return (
    <tr
      data-testid="all-reviews-row"
      data-review-id={row.id}
      title={detail}
      className={`border-t border-[var(--border-subtle)] hover:bg-[var(--surface-app)] ${down ? "text-[var(--text-secondary)]" : ""}`}
    >
      <td className="px-3 py-[10px]">
        <span className="flex items-center gap-[10px]">
          <ProductThumbnail url={row.product.image_url} size={32} />
          <span className="flex min-w-0 flex-col gap-1 leading-4 [&>:first-child]:leading-5">
            <Link href={`/reviews/${row.id}`} className="truncate hover:underline">
              {product}
            </Link>
            <span className="truncate text-[12px] text-[var(--text-secondary)]">by {author}</span>
          </span>
        </span>
        <span className="sr-only">
          {" "}Review “{row.title}”. Gate Wilson{" "}
          <span data-testid="all-reviews-gate">{row.gate.wilson_lower_bound.toFixed(2)}</span>. Votes{" "}
          <span data-testid="all-reviews-votes">
            {row.helpful_votes} / {row.unhelpful_votes}
          </span>
          . <span data-testid="all-reviews-queue-status">{queue}</span>
        </span>
      </td>
      <td className="whitespace-nowrap px-3">{levelLabel(row.author?.trust_stage)}</td>
      <td className="px-3 [font-variant-numeric:tabular-nums]" data-testid="all-reviews-rating">
        <RatingCell rating={rating} muted={down} />
      </td>
      <td className="px-3">
        <EarningCell path={earningPath({ ...row, star_rating: rating })} />
      </td>
      <td className="px-3 [font-variant-numeric:tabular-nums]" data-testid="all-reviews-wilson">
        {wilsonText(row.wilson_score)}
      </td>
      <td className={`whitespace-nowrap px-3 ${STATE_TONE[row.state]}`}>{STATE_LABELS[row.state]}</td>
      <td className="whitespace-nowrap px-3 text-[var(--text-secondary)]" suppressHydrationWarning>
        {postedText(row.published_at ?? row.created_at, now)}
      </td>
    </tr>
  );
}

const SORTS = Object.entries(SORT_LABELS) as [AllReviewsSort, string][];
const STATES = Object.entries(STATE_LABELS) as [AllReviewsState, string][];
const EARNS = Object.entries(EARN_LABELS) as [EarnState, string][];

function FilterChip({ href, active, label }: { href: string; active: boolean; label: string }) {
  return (
    <Link
      href={href}
      scroll={false}
      aria-pressed={active}
      className={`inline-flex h-8 items-center rounded-full border px-3 text-[14px] leading-none ${
        active
          ? "border-[var(--base-ink-800)] bg-[var(--base-ink-800)] text-white"
          : "border-[var(--border-subtle)] hover:border-[var(--text-secondary)]"
      }`}
    >
      {label}
    </Link>
  );
}

/**
 * The toolbar's Sort / Filter / Search for All reviews, beside the Queue
 * switch (Toolbar of 8060:15564). Filters: state, earning state and the posted
 * day range — the backend's own parameters; "Clear all" resets them and closes.
 */
export function AllReviewsControls({ filters }: { filters: AllReviewsFilters }) {
  const router = useRouter();
  const { open: sortOpen, setOpen: setSortOpen, ref: sortRef } = usePopover();
  const { open: filterOpen, setOpen: setFilterOpen, ref: filterRef } = usePopover();
  const { open: searchOpen, setOpen: setSearchOpen, ref: searchRef } = usePopover();
  const [q, setQ] = useState(filters.q);
  const [from, setFrom] = useState(filters.from);
  const [to, setTo] = useState(filters.to);
  const active = activeFilterCount(filters);

  return (
    <div className="flex items-center gap-1">
      <div ref={sortRef} className="relative">
        <button type="button" onClick={() => setSortOpen(!sortOpen)} aria-expanded={sortOpen} aria-label="Sort" className={ICON_BUTTON}>
          <ArrowsDownUp size={18} />
        </button>
        {sortOpen ? (
          <ul className={`${MENU} w-[220px] p-2`} role="menu" aria-label="Sort">
            {SORTS.map(([key, label]) => (
              <li key={key} role="none">
                <Link
                  role="menuitemradio"
                  aria-checked={filters.sort === key}
                  href={allReviewsHref(filters, { sort: key })}
                  scroll={false}
                  onClick={() => setSortOpen(false)}
                  className={MENU_ITEM}
                >
                  {label}
                  {filters.sort === key ? <Check size={16} aria-hidden /> : null}
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
      </div>

      <div ref={filterRef} className="relative">
        <button
          type="button"
          onClick={() => setFilterOpen(!filterOpen)}
          aria-expanded={filterOpen}
          aria-label={active ? `Filters, ${active} on` : "Filters"}
          className={ICON_BUTTON}
        >
          <SlidersHorizontal size={18} />
          {active ? <span aria-hidden className="absolute right-1 top-1 size-[6px] rounded-full bg-[var(--accent-primary)]" /> : null}
        </button>
        {filterOpen ? (
          <div role="group" aria-label="Filters" className={`${MENU} flex w-[380px] flex-col gap-4 p-4`}>
            <Group title="State">
              {STATES.map(([key, label]) => (
                <FilterChip
                  key={key}
                  label={label}
                  active={filters.state === key}
                  href={allReviewsHref(filters, { state: filters.state === key ? "" : key })}
                />
              ))}
            </Group>
            <Group title="Earning">
              {EARNS.map(([key, label]) => (
                <FilterChip
                  key={key}
                  label={label}
                  active={filters.earn === key}
                  href={allReviewsHref(filters, { earn: filters.earn === key ? "" : key })}
                />
              ))}
            </Group>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                router.push(allReviewsHref(filters, { from, to }), { scroll: false });
              }}
              className="flex flex-col gap-2"
            >
              <p className="text-[12px] text-[var(--text-secondary)]">Posted</p>
              <div className="flex items-center gap-2 text-[12px]">
                <label className="flex items-center gap-1">
                  From
                  <input type="date" value={from} onChange={(e) => setFrom(e.target.value)} className="h-8 rounded-[8px] border border-[var(--border-subtle)] px-2" />
                </label>
                <label className="flex items-center gap-1">
                  To
                  <input type="date" value={to} onChange={(e) => setTo(e.target.value)} className="h-8 rounded-[8px] border border-[var(--border-subtle)] px-2" />
                </label>
                <button type="submit" className="h-8 rounded-full border border-[var(--text-primary)] px-3">
                  Apply
                </button>
              </div>
            </form>
            <Link
              href={allReviewsHref(filters, { state: "", earn: "", from: "", to: "" })}
              scroll={false}
              onClick={() => setFilterOpen(false)}
              className="self-start border-t border-[var(--border-subtle)] pt-3 text-[14px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
            >
              Clear all
            </Link>
          </div>
        ) : null}
      </div>

      <div ref={searchRef} className="relative">
        <button
          type="button"
          onClick={() => setSearchOpen(!searchOpen)}
          aria-expanded={searchOpen}
          aria-label="Search all reviews"
          className={ICON_BUTTON}
        >
          <MagnifyingGlass size={18} />
          {filters.q ? <span aria-hidden className="absolute right-1 top-1 size-[6px] rounded-full bg-[var(--accent-primary)]" /> : null}
        </button>
        {searchOpen ? (
          <form
            role="search"
            onSubmit={(e) => {
              e.preventDefault();
              router.push(allReviewsHref(filters, { q: q.trim() }), { scroll: false });
              setSearchOpen(false);
            }}
            className={`${MENU} flex w-[340px] items-center gap-2 p-2`}
          >
            <label className="sr-only" htmlFor="all-reviews-q">
              Title, text, product, author or reference
            </label>
            <input
              id="all-reviews-q"
              value={q}
              autoFocus
              onChange={(e) => setQ(e.target.value)}
              placeholder="Title, text, product, author or BR- reference"
              maxLength={200}
              className={`h-9 min-w-0 flex-1 rounded-[10px] px-3 text-[12px] caret-[var(--accent-primary)] outline-none placeholder:text-[var(--text-secondary)] ${TOP_SEARCH_STATES}`}
            />
            <button type="submit" className="h-9 rounded-full border border-[var(--text-primary)] px-3 text-[12px]">
              Search
            </button>
          </form>
        ) : null}
      </div>
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="flex flex-col gap-2">
      <p className="text-[12px] text-[var(--text-secondary)]">{title}</p>
      <div className="flex flex-wrap gap-2">{children}</div>
    </div>
  );
}
