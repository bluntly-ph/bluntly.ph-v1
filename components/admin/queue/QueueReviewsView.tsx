"use client";

import Image from "next/image";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useCallback, useMemo, useState } from "react";
import {
  ArrowsDownUp,
  Camera,
  Check,
  MagnifyingGlass,
  Package,
  Receipt,
  SlidersHorizontal,
} from "@phosphor-icons/react/dist/ssr";

import {
  EarningCell,
  RatingCell,
  TierCell,
  earningPath,
  levelLabel,
} from "@/components/admin/queue/QueueCells";
import { QueueReviewModal } from "@/components/admin/queue/QueueReviewModal";
import { Pagination } from "@/components/console/Pagination";
import { ICON_BUTTON, MENU, usePopover } from "@/components/console/popover";
import {
  PRIORITY_TIERS,
  QUEUE_LIMITS,
  QUEUE_VIEWS,
  QUEUE_VIEW_LABELS,
  TIER_LABELS,
  queueAgeLabel,
  queueHref,
  type QueueFilters,
  type QueueSort,
} from "@/components/admin/review-queue-model";
import type { QueueItem, QueueResult, ReportItem } from "@/lib/moderation";
import { SEARCH_INPUT, TOOLBAR_SEARCH_STATES } from "@/components/ui/search-styles";
import { MENU_ITEM } from "@/components/console/fields";

/**
 * The Reviews view of the redesigned queue (Screen/Admin/Queue/Reviews
 * 7943:11402): the full-width table, its sort / filter / search controls
 * (Menu/Reviews/Sort 7958:10978, Menu/Reviews/Filter 7958:10988,
 * Search/Reviews 7958:11058) and the pagination under it. A row opens the
 * review in a modal; `?open=<review id>` opens it from a link.
 *
 * Every control changes the URL and the server answers: the queue is ordered
 * and filtered over the whole backlog before the page is cut, so nothing here
 * filters or sorts the rows it happens to hold.
 */

const EDITED_FACTOR = "edited_after_monetization";

const SORTS: [QueueSort, string][] = [
  ["tier", "Priority tier"],
  ["policy", "Policy order"],
  ["oldest", "Oldest first"],
];
const BANDS: [string, string][] = [["high", "High"], ["normal", "Normal"], ["low", "Low"]];
const SLAS: [string, string][] = [["on_track", "On track"], ["approaching", "Approaching"], ["overdue", "Overdue"]];
const LANES: [string, string][] = [
  ["escalated", "Escalated"],
  ["reported", "Reported"],
  ["integrity", "Integrity"],
  ["routine", "Routine"],
  ["quality_audit", "Quality audit"],
];

function Chip({ href, active, label, count }: { href: string; active: boolean; label: string; count?: number }) {
  return (
    <Link
      href={href}
      scroll={false}
      aria-current={active ? "true" : undefined}
      className={`inline-flex items-center gap-1.5 rounded-full border px-3 py-1.5 text-[14px] leading-none ${
        active
          ? "border-[var(--base-ink-800)] bg-[var(--base-ink-800)] text-white"
          : "border-[var(--border-subtle)] hover:border-[var(--text-secondary)]"
      }`}
    >
      {label}
      {count !== undefined ? (
        <span className={`text-[12px] ${active ? "text-white/80" : "text-[var(--text-secondary)]"}`}>{count}</span>
      ) : null}
    </Link>
  );
}

/** The sort, filter and search controls at the toolbar's right end. */
export function ReviewsControls({ queue, filters }: { queue: QueueResult; filters: QueueFilters }) {
  const { open: sortOpen, setOpen: setSortOpen, ref: sortRef } = usePopover();
  const { open: filterOpen, setOpen: setFilterOpen, ref: filterRef } = usePopover();
  const { open: searchOpen, setOpen: setSearchOpen, ref: searchRef } = usePopover();
  const counts = queue.available ? queue.counts : null;
  const active = [filters.tier, filters.band, filters.sla, filters.lane, filters.factor,
    filters.view === "taken_down" ? "taken_down" : ""].filter(Boolean).length;

  return (
    <div className="flex items-center gap-1">
      <div ref={sortRef} className="relative">
        <button type="button" onClick={() => setSortOpen(!sortOpen)} aria-expanded={sortOpen} aria-label="Sort" className={ICON_BUTTON}>
          <ArrowsDownUp size={18} />
        </button>
        {sortOpen ? (
          <ul className={`${MENU} w-[220px] p-2`} role="menu">
            {SORTS.map(([key, label]) => (
              <li key={key} role="none">
                <Link
                  role="menuitemradio"
                  aria-checked={filters.sort === key}
                  href={queueHref(filters, { sort: key })}
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
          className={`${ICON_BUTTON} relative`}
        >
          <SlidersHorizontal size={18} />
          {active ? (
            <span className="absolute right-1 top-1 size-[7px] rounded-full bg-[var(--accent-primary)]" aria-hidden />
          ) : null}
        </button>
        {filterOpen ? (
          <div className={`${MENU} flex w-[340px] max-w-[calc(100vw-32px)] flex-col gap-4 p-4`}>
            {/* MQA-015: decided reviews leave the work; Taken down keeps them reachable. */}
            <FilterGroup title="Show">
              {QUEUE_VIEWS.map((v) => (
                <Chip
                  key={v}
                  href={queueHref(filters, { view: v })}
                  active={(filters.view ?? "waiting") === v}
                  label={QUEUE_VIEW_LABELS[v]}
                  count={counts?.by_view?.[v]}
                />
              ))}
            </FilterGroup>
            <FilterGroup title="Tier">
              {PRIORITY_TIERS.map((t) => (
                <Chip
                  key={t}
                  href={queueHref(filters, { tier: filters.tier === t ? "" : t })}
                  active={filters.tier === t}
                  label={TIER_LABELS[t]}
                  count={counts?.by_tier?.[t]}
                />
              ))}
            </FilterGroup>
            <FilterGroup title="Band">
              {BANDS.map(([b, label]) => (
                <Chip
                  key={b}
                  href={queueHref(filters, { band: (filters.band === b ? "" : b) as QueueFilters["band"] })}
                  active={filters.band === b}
                  label={label}
                  count={counts?.by_band?.[b]}
                />
              ))}
            </FilterGroup>
            <FilterGroup title="SLA">
              {SLAS.map(([s, label]) => (
                <Chip
                  key={s}
                  href={queueHref(filters, { sla: (filters.sla === s ? "" : s) as QueueFilters["sla"] })}
                  active={filters.sla === s}
                  label={label}
                  count={counts?.by_sla?.[s]}
                />
              ))}
            </FilterGroup>
            <FilterGroup title="Lane">
              {LANES.map(([l, label]) => (
                <Chip
                  key={l}
                  href={queueHref(filters, { lane: (filters.lane === l ? "" : l) as QueueFilters["lane"] })}
                  active={filters.lane === l}
                  label={label}
                  count={counts?.by_lane?.[l]}
                />
              ))}
            </FilterGroup>
            <FilterGroup title="Signal">
              <Chip
                href={queueHref(filters, { factor: filters.factor === EDITED_FACTOR ? "" : EDITED_FACTOR })}
                active={filters.factor === EDITED_FACTOR}
                label="Edited after link"
              />
            </FilterGroup>
            <div className="-mx-4 -mb-1 border-t border-[var(--border-subtle)] px-4 pt-3">
              <Link
                href={queueHref(filters, { tier: "", band: "", sla: "", lane: "", factor: "" })}
                scroll={false}
                onClick={() => setFilterOpen(false)}
                className="text-[14px] text-[var(--accent-trust)] hover:underline"
              >
                Clear all
              </Link>
            </div>
          </div>
        ) : null}
      </div>

      <div ref={searchRef} className="relative">
        <button
          type="button"
          onClick={() => setSearchOpen(!searchOpen)}
          aria-expanded={searchOpen}
          aria-label="Search the queue"
          className={`${ICON_BUTTON} relative`}
        >
          <MagnifyingGlass size={18} />
          {filters.q ? <span className="absolute right-1 top-1 size-[7px] rounded-full bg-[var(--accent-primary)]" aria-hidden /> : null}
        </button>
        {searchOpen ? (
          <form action="/admin/review-queue" method="get" className={`${MENU} w-[360px] max-w-[calc(100vw-32px)] p-0`}>
            {filters.tier ? <input type="hidden" name="tier" value={filters.tier} /> : null}
            {filters.band ? <input type="hidden" name="band" value={filters.band} /> : null}
            {filters.sla ? <input type="hidden" name="sla" value={filters.sla} /> : null}
            {filters.lane ? <input type="hidden" name="lane" value={filters.lane} /> : null}
            {filters.factor ? <input type="hidden" name="factor" value={filters.factor} /> : null}
            {filters.sort !== "tier" ? <input type="hidden" name="sort" value={filters.sort} /> : null}
            {/* Admin/ToolbarSearch (8270:28869). */}
            <label className={`m-2 flex h-9 items-center gap-2 rounded-[32px] pl-[14px] pr-3 ${TOOLBAR_SEARCH_STATES}`}>
              <MagnifyingGlass size={16} className="text-[var(--text-secondary)]" />
              <span className="sr-only">Search title, product or review body</span>
              <input
                autoFocus
                type="search"
                name="q"
                defaultValue={filters.q}
                placeholder="Search title, product or review body"
                className={`${SEARCH_INPUT} text-[12px] placeholder:text-[var(--text-secondary)]`}
              />
            </label>
          </form>
        ) : null}
      </div>
    </div>
  );
}

function FilterGroup({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <p className="pb-2 text-[12px] text-[var(--accent-trust)]">{title}</p>
      <div className="flex flex-wrap gap-1.5">{children}</div>
    </div>
  );
}

/** The table, the pagination and the review modal. */
export function ReviewsTable({
  queue,
  filters,
  reports,
  now,
  openItem,
}: {
  queue: QueueResult;
  filters: QueueFilters;
  reports: ReportItem[];
  now: number;
  /** A review asked for by `?open=` that is not on this page. */
  openItem?: QueueItem | null;
}) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const items = useMemo(() => (queue.available ? queue.items : []), [queue]);
  const total = queue.available ? queue.total : 0;
  const [openId, setOpenId] = useState<string | null>(searchParams?.get("open") ?? null);

  const setOpen = useCallback((id: string | null) => {
    setOpenId(id);
    // Shareable without a round trip: Next keeps useSearchParams in sync with
    // history.replaceState.
    const params = new URLSearchParams(window.location.search);
    if (id) params.set("open", id);
    else params.delete("open");
    const query = params.toString();
    window.history.replaceState(null, "", query ? `?${query}` : window.location.pathname);
  }, []);

  const index = items.findIndex((i) => i.review.id === openId);
  const current = index >= 0 ? items[index] : openItem && openItem.review.id === openId ? openItem : null;

  const step = useCallback(
    (delta: number) => {
      if (index < 0) return;
      const next = items[index + delta];
      if (next) setOpen(next.review.id);
      else if (delta > 0 && filters.offset + items.length < total) {
        router.push(queueHref(filters, { offset: filters.offset + filters.limit }), { scroll: false });
      } else if (delta < 0 && filters.offset > 0) {
        router.push(queueHref(filters, { offset: Math.max(0, filters.offset - filters.limit) }), { scroll: false });
      }
    },
    [index, items, filters, total, router, setOpen],
  );

  if (!queue.available) {
    return (
      <p role="alert" className="rounded-[16px] border border-[var(--border-subtle)] p-6 text-[14px] text-[var(--text-secondary)]">
        {queue.reason === "unauthenticated"
          ? "Your session has ended. Sign in again to see the queue."
          : "The queue could not be loaded. Nothing is wrong with the reviews; try again in a moment."}
      </p>
    );
  }

  const page = Math.floor(filters.offset / filters.limit) + 1;
  const takenDownView = filters.view === "taken_down";
  const takenDown = queue.counts?.by_view?.taken_down ?? 0;

  return (
    <>
      {/* MQA-015: a decided review leaves the list of work; the ones a moderator
          took down stay one switch away, with Restore on their card. */}
      {takenDownView ? (
        <p data-testid="queue-view-note" className="mb-3 flex flex-wrap items-center gap-x-3 gap-y-1 text-[13px] text-[var(--text-secondary)]">
          <span>Taken down by a moderator: off the site and not counted in the queue. Open one to restore it.</span>
          <Link href={queueHref(filters, { view: "waiting" })} scroll={false} className="text-[var(--text-primary)] underline underline-offset-4">
            Back to reviews waiting for a decision
          </Link>
        </p>
      ) : takenDown > 0 ? (
        <p data-testid="queue-view-note" className="mb-3 text-[13px] text-[var(--text-secondary)]">
          <Link href={queueHref(filters, { view: "taken_down" })} scroll={false} className="underline underline-offset-4 hover:text-[var(--text-primary)]">
            {takenDown} taken down
          </Link>{" "}
          — decided, so not in this list.
        </p>
      ) : null}
      <div className="overflow-x-auto rounded-[16px] border border-[var(--border-subtle)]">
        <table className="w-full min-w-[960px] table-fixed border-collapse text-left text-[14px]">
          <caption className="sr-only">{takenDownView ? "Reviews taken down by a moderator" : "Reviews waiting for a decision"}</caption>
          <colgroup>
            <col style={{ width: "31%" }} />
            <col style={{ width: "15%" }} />
            <col style={{ width: "8%" }} />
            <col style={{ width: "14%" }} />
            <col style={{ width: "9%" }} />
            <col style={{ width: "13%" }} />
            <col style={{ width: "10%" }} />
          </colgroup>
          <thead className="bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
            <tr>
              <th scope="col" className="h-10 px-3 font-normal">Review</th>
              <th scope="col" className="px-3 font-normal">Level</th>
              <th scope="col" className="px-3 font-normal">Rating</th>
              <th scope="col" className="px-3 font-normal">Earnings</th>
              <th scope="col" className="px-3 text-center font-normal">Evidence</th>
              <th scope="col" className="px-3 font-normal">Priority</th>
              <th scope="col" className="px-3 font-normal">Age</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 ? (
              <tr>
                <td colSpan={7} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">
                  {filters.q || filters.tier || filters.band || filters.sla || filters.lane || filters.factor
                    ? "Nothing matches these filters."
                    : "Nothing is waiting. Every review has an earnings decision."}
                </td>
              </tr>
            ) : (
              items.map((item) => {
                const path = earningPath(item.review);
                const down = path === "taken_down";
                const overdue = item.priority.sla_state === "overdue";
                return (
                  <tr
                    key={item.review.id}
                    onClick={() => setOpen(item.review.id)}
                    className={`cursor-pointer border-t border-[var(--border-subtle)] hover:bg-[var(--surface-app)]/60 ${
                      down ? "bg-[var(--surface-app)]/70 text-[var(--text-secondary)]" : ""
                    }`}
                  >
                    <td className="px-3 py-[10px]" title={item.review.title}>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setOpen(item.review.id);
                        }}
                        className="flex w-full items-center gap-[10px] text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
                      >
                        <span className={`relative grid size-8 shrink-0 place-items-center overflow-hidden rounded-[8px] bg-[var(--surface-app)] ${down ? "opacity-50" : ""}`}>
                          {item.review.photo_url ? (
                            <Image src={item.review.photo_url} alt="" fill sizes="32px" className="object-cover" />
                          ) : (
                            <Package size={16} className="text-[var(--text-muted)]" aria-hidden />
                          )}
                        </span>
                        <span className="flex min-w-0 flex-col gap-1 leading-4 [&>:first-child]:leading-5">
                          <span className="truncate">{item.product.canonical_name ?? item.review.title}</span>
                          <span className="truncate text-[12px] text-[var(--text-secondary)]">
                            by {item.author?.display_name ?? "a former member"}
                          </span>
                        </span>
                      </button>
                    </td>
                    <td className="px-3">{levelLabel(item.author?.trust_stage)}</td>
                    <td className="px-3">
                      <RatingCell rating={item.review.star_rating} muted={down} />
                    </td>
                    <td className="px-3">
                      <EarningCell path={path} />
                    </td>
                    <td className="px-3">
                      <span className="flex items-center justify-center gap-[10px]">
                        <Receipt
                          size={16}
                          className={item.review.has_receipt ? "text-[var(--accent-success)]" : "text-[var(--text-muted)]"}
                          aria-label={item.review.has_receipt ? "Receipt attached" : "No receipt"}
                        />
                        <Camera
                          size={16}
                          className={item.review.photo_url ? "text-[var(--accent-success)]" : "text-[var(--text-muted)]"}
                          aria-label={item.review.photo_url ? "Photo attached" : "No photo"}
                        />
                      </span>
                    </td>
                    <td className="px-3">{down ? "—" : <TierCell tier={item.triage?.tier} />}</td>
                    <td className={`px-3 ${overdue && !down ? "text-[var(--accent-danger)]" : ""}`}>
                      {queueAgeLabel(item, now)}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>

      <div className="mt-4">
        <Pagination
          page={page}
          size={filters.limit}
          total={total}
          sizes={QUEUE_LIMITS}
          hrefFor={(p, size) => queueHref(filters, { limit: size, offset: (p - 1) * size })}
          label="Queue pages"
        />
      </div>

      {current ? (
        <QueueReviewModal
          key={current.review.id}
          item={current}
          index={index >= 0 ? index : 0}
          total={index >= 0 ? total : 1}
          offset={index >= 0 ? filters.offset : 0}
          reports={reports}
          now={now}
          onClose={() => setOpen(null)}
          onStep={step}
        />
      ) : null}
    </>
  );
}
