"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import { ArrowsDownUp, Check, MagnifyingGlass, SlidersHorizontal } from "@phosphor-icons/react/dist/ssr";

import { AdminModal } from "@/components/admin/AdminModal";
import { ConfirmDialog } from "@/components/admin/ConfirmDialog";
import { PersonCell } from "@/components/admin/queue/QueueCells";
import { countState } from "@/components/console/counted-model";
import { CountedTextarea } from "@/components/console/CountedTextarea";
import { Chip } from "@/components/console/Chip";
import { Pagination } from "@/components/console/Pagination";
import { ICON_BUTTON, MENU, usePopover } from "@/components/console/popover";
import { StarRow } from "@/components/sellers/SellerIdentity";
import { formatRating } from "@/components/ui/star-ladder";

import { APPEAL_KINDS, appealKind, type AppealKind } from "./appeal-kinds";
import { agoShort } from "./overview-model";
import { oldestAwaiting } from "./quick-actions-model";
import {
  ORDER_LABEL,
  REVIEW_COLUMNS,
  SORTS,
  TABS,
  applyFilters,
  facets,
  inTab,
  orderState,
  reviewerName,
  sortReviews,
  type OrderState,
  type ReviewFilters,
  type ReviewSort,
  type ReviewTab,
  type StoreReview,
} from "./reviews-model";
import { TOP_SEARCH_STATES } from "@/components/ui/search-styles";
import { MENU_ITEM } from "@/components/console/fields";

/**
 * Screen/Seller/Reviews (Figma 8196:20870, Responded 8201:21535, All
 * 8201:22036) with Overlay/Store/Respond 8197:21320, EditResponse 8202:22435,
 * FlagFake 8197:21432 and their confirms (8202:22581, 8202:22699, 8202:22623).
 *
 * Responding is all a claim grants over a review (§9): the store posts or edits
 * its one public response (POST /sellers/reviews/{id}/response) or flags a
 * review as suspected fake (POST …/appeal, once per review while one is open).
 * Nothing here hides or removes a review.
 */

const MAX = 1000;
const NONE: ReviewFilters = { stars: [], order: [], recommend: [], q: "" };

type Summary = { reviewCount: number; responses: number; responseRate: number | null; medianReplyHours: number | null };

function problem(p: unknown, fallback: string): string {
  const d = (p as { detail?: unknown })?.detail;
  return typeof d === "string" ? d : fallback;
}

export function SellerReviews({
  storeName,
  reviews,
  flagged,
  summary,
  capped,
  respondTo = null,
  now,
}: {
  storeName: string;
  reviews: StoreReview[];
  /** Reviews with a flag still open: no second flag offered. */
  flagged: string[];
  summary: Summary;
  /** The list stopped at the newest 1,000: say so instead of implying it is all. */
  capped: boolean;
  /** ?respond= on arrival: "oldest" (Quick actions) or a review's id (Overview). Opens Respond on it. */
  respondTo?: string | null;
  now: number;
}) {
  const router = useRouter();
  const [tab, setTab] = useState<ReviewTab>("needs");
  const [sort, setSort] = useState<ReviewSort>("oldest");
  const [filters, setFilters] = useState<ReviewFilters>(NONE);
  const [page, setPage] = useState({ page: 1, size: 10 });
  const [respond, setRespond] = useState<StoreReview | null>(() =>
    respondTo === "oldest" ? oldestAwaiting(reviews) : (reviews.find((r) => r.id === respondTo) ?? null),
  );
  const [flag, setFlag] = useState<StoreReview | null>(null);
  const { open: sortOpen, setOpen: setSortOpen, ref: sortRef } = usePopover();
  const { open: filterOpen, setOpen: setFilterOpen, ref: filterRef } = usePopover();
  const { open: searchOpen, setOpen: setSearchOpen, ref: searchRef } = usePopover();

  const counts = { needs: 0, responded: 0, all: reviews.length };
  for (const r of reviews) counts[r.seller_response ? "responded" : "needs"] += 1;
  const inThisTab = useMemo(() => reviews.filter((r) => inTab(r, tab)), [reviews, tab]);
  const shown = useMemo(() => sortReviews(applyFilters(inThisTab, filters), sort), [inThisTab, filters, sort]);
  const facet = facets(inThisTab);
  const rows = shown.slice((page.page - 1) * page.size, page.page * page.size);
  const oldestWaiting = reviews.filter((r) => !r.seller_response).map((r) => new Date(r.created_at).getTime()).sort((a, b) => a - b)[0];
  const active = filters.stars.length + filters.order.length + filters.recommend.length;
  const flaggedSet = new Set(flagged);
  const change = (next: Partial<ReviewFilters>) => {
    setFilters((f) => ({ ...f, ...next }));
    setPage((p) => ({ ...p, page: 1 }));
  };
  const toggle = <T,>(list: T[], v: T) => (list.includes(v) ? list.filter((x) => x !== v) : [...list, v]);

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-[24px] font-semibold leading-none">Reviews</h1>
      <div className="flex flex-wrap items-center gap-2">
        <nav aria-label="Review views" className="flex flex-wrap gap-[2px] rounded-[10px] bg-[var(--surface-app)] p-[3px]">
          {TABS.map((t) => (
            <button
              key={t.key}
              type="button"
              aria-current={tab === t.key ? "page" : undefined}
              onClick={() => {
                setTab(t.key);
                setPage((p) => ({ ...p, page: 1 }));
              }}
              className={`flex items-center gap-[6px] rounded-[8px] px-3 py-[5px] leading-none ${
                tab === t.key ? "bg-[var(--surface-card)] shadow-[var(--shadow-segment)]" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              }`}
            >
              <span className="text-[14px] font-medium">{t.label}</span>
              <span className="text-[12px] text-[var(--text-secondary)]">{counts[t.key]}</span>
            </button>
          ))}
        </nav>
        <span className="flex-1" />
        <div ref={sortRef} className="relative">
          <button type="button" aria-label="Sort" aria-expanded={sortOpen} onClick={() => setSortOpen(!sortOpen)} className={ICON_BUTTON}>
            <ArrowsDownUp size={18} />
          </button>
          {sortOpen ? (
            <ul role="menu" aria-label="Sort" className={`${MENU} w-[220px] p-2`}>
              {SORTS.map((s) => (
                <li key={s.key} role="none">
                  <button
                    type="button"
                    role="menuitemradio"
                    aria-checked={sort === s.key}
                    onClick={() => {
                      setSort(s.key);
                      setSortOpen(false);
                    }}
                    className={MENU_ITEM}
                  >
                    {s.label}
                    {sort === s.key ? <Check size={16} aria-hidden /> : null}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
        </div>
        <div ref={filterRef} className="relative">
          <button
            type="button"
            aria-label={active ? `Filters, ${active} on` : "Filters"}
            aria-expanded={filterOpen}
            onClick={() => setFilterOpen(!filterOpen)}
            className={ICON_BUTTON}
          >
            <SlidersHorizontal size={18} />
            {active ? <span aria-hidden className="absolute right-1 top-1 size-[6px] rounded-full bg-[var(--accent-primary)]" /> : null}
          </button>
          {filterOpen ? (
            <div role="group" aria-label="Filters" className={`${MENU} flex w-[340px] flex-col gap-4 p-4`}>
              <Group title="Rating">
                {[1, 2, 3, 4, 5].map((n) => (
                  <Facet key={n} label={`${n}★`} count={facet.stars[n]} on={filters.stars.includes(n)} onClick={() => change({ stars: toggle(filters.stars, n) })} />
                ))}
              </Group>
              <Group title="Order">
                {(["not_as_listed", "missing", "as_listed"] as OrderState[]).map((o) => (
                  <Facet key={o} label={o === "as_listed" ? "As listed" : ORDER_LABEL[o]} count={facet.order[o]} on={filters.order.includes(o)} onClick={() => change({ order: toggle(filters.order, o) })} />
                ))}
              </Group>
              <Group title="Would recommend">
                {(["yes", "no"] as const).map((v) => (
                  <Facet key={v} label={v === "yes" ? "Yes" : "No"} count={facet.recommend[v]} on={filters.recommend.includes(v)} onClick={() => change({ recommend: toggle(filters.recommend, v) })} />
                ))}
              </Group>
              <button
                type="button"
                onClick={() => {
                  change({ stars: [], order: [], recommend: [] });
                  setFilterOpen(false);
                }}
                className="self-start border-t border-[var(--border-subtle)] pt-3 text-[14px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
              >
                Clear all
              </button>
            </div>
          ) : null}
        </div>
        <div ref={searchRef} className="relative">
          <button type="button" aria-label="Search reviews" aria-expanded={searchOpen} onClick={() => setSearchOpen(!searchOpen)} className={ICON_BUTTON}>
            <MagnifyingGlass size={18} />
            {filters.q ? <span aria-hidden className="absolute right-1 top-1 size-[6px] rounded-full bg-[var(--accent-primary)]" /> : null}
          </button>
          {searchOpen ? (
            <div role="search" className={`${MENU} w-[360px] p-2`}>
              <label className="sr-only" htmlFor="seller-reviews-q">Search reviews</label>
              <input
                id="seller-reviews-q"
                autoFocus
                value={filters.q}
                onChange={(e) => change({ q: e.target.value })}
                placeholder="Search a buyer, title or words in the review"
                className={`h-9 w-full rounded-[10px] px-3 text-[12px] caret-[var(--accent-primary)] outline-none placeholder:text-[var(--text-secondary)] ${TOP_SEARCH_STATES}`}
              />
            </div>
          ) : null}
        </div>
      </div>

      <section aria-label="Responses at a glance" className="grid gap-3 sm:grid-cols-3">
        <Card label="Needs response" value={String(counts.needs)} note={oldestWaiting ? `Oldest has waited ${agoShort(new Date(oldestWaiting).toISOString(), now).replace(" ago", "")}` : "Nothing waiting"} />
        <Card
          label="Response rate"
          value={summary.responseRate != null ? `${Math.round(summary.responseRate * 100)}%` : "—"}
          note={`${summary.responses} of ${summary.reviewCount} reviews`}
        />
        <Card label="Median reply time" value={summary.medianReplyHours != null ? hours(summary.medianReplyHours) : "—"} note="Reviews and store questions, all time" />
      </section>

      <div className="overflow-x-auto rounded-[16px] border border-[var(--border-subtle)]">
        <table className="w-full min-w-[960px] border-collapse text-left text-[14px]">
          <caption className="sr-only">Reviews of {storeName}</caption>
          <thead className="bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
            <tr>
              {REVIEW_COLUMNS[tab].map((h) => (
                <th key={h} scope="col" className="h-10 px-3 font-normal">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">
                  {reviews.length === 0
                    ? "No reviews of your store yet."
                    : tab === "needs" && !active && !filters.q
                      ? "Every review has your response."
                      : "No review matches."}
                </td>
              </tr>
            ) : (
              rows.map((r) => {
                const o = orderState(r);
                return (
                  <tr key={r.id} data-testid="seller-review-row" className="group border-t border-[var(--border-subtle)] align-top hover:bg-[var(--surface-app)]">
                    <td className="px-3 py-[10px]">
                      <PersonCell name={reviewerName(r)} stage={r.reviewer?.trust_stage ?? null} />
                    </td>
                    <td className="px-3 py-[14px]">
                      <span className="sr-only">{formatRating(r.overall_rating)} stars</span>
                      <StarRow value={r.overall_rating} size={16} />
                    </td>
                    <td className="max-w-[360px] px-3 py-[10px]">
                      <span className="flex flex-col gap-1">
                        <span className="truncate">{r.title || r.comment || "Untitled review"}</span>
                        {tab === "needs" && r.title ? <span className="line-clamp-1 text-[12px] text-[var(--text-secondary)]">{r.comment}</span> : null}
                      </span>
                    </td>
                    {tab === "needs" ? (
                      <td className="px-3 py-[14px]">
                        {/* Figma 8196:20870 draws a problem as danger text, not a chip. */}
                        <span className={`text-[12px] ${o === "as_listed" ? "text-[var(--text-secondary)]" : "text-[var(--status-critical-fg)]"}`}>{ORDER_LABEL[o]}</span>
                      </td>
                    ) : tab === "responded" ? (
                      <td className="max-w-[320px] px-3 py-[14px]">
                        <span className="line-clamp-1 text-[var(--text-secondary)]">{r.seller_response}</span>
                      </td>
                    ) : (
                      <td className="px-3 py-[12px]">
                        {r.seller_response ? <Chip tone="success">Responded</Chip> : <Chip tone="warning">No response</Chip>}
                      </td>
                    )}
                    <td className="whitespace-nowrap px-3 py-[14px] text-[var(--text-secondary)]" suppressHydrationWarning>
                      {agoShort(tab === "responded" && r.seller_response_at ? r.seller_response_at : r.created_at, now)}
                    </td>
                    <td className="px-3 py-[10px]">
                      <button
                        type="button"
                        onClick={() => setRespond(r)}
                        className="h-8 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 text-[12px] hover:border-[var(--text-secondary)]"
                      >
                        {r.seller_response ? "Edit" : "Respond"}
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      <Pagination page={page.page} size={page.size} total={shown.length} onChange={setPage} label="Review pages" />
      {capped ? <p className="text-[12px] text-[var(--text-secondary)]">Showing your newest 1,000 reviews.</p> : null}

      {respond ? (
        <RespondModal
          key={respond.id}
          review={respond}
          storeName={storeName}
          canFlag={!respond.seller_response && !flaggedSet.has(respond.id)}
          onFlag={() => {
            setFlag(respond);
            setRespond(null);
          }}
          onClose={() => {
            setRespond(null);
            // Drop ?respond= so a refresh doesn't open it again.
            if (respondTo) router.replace(window.location.pathname, { scroll: false });
          }}
          now={now}
        />
      ) : null}
      {flag ? <FlagModal key={flag.id} review={flag} onClose={() => setFlag(null)} now={now} /> : null}
    </div>
  );
}

function hours(h: number): string {
  if (h < 1) return `${Math.max(1, Math.round(h * 60))} min`;
  if (h < 48) return `${Math.round(h)} h`;
  return `${Math.round(h / 24)} days`;
}

function Card({ label, value, note }: { label: string; value: string; note: string }) {
  return (
    <div className="flex flex-col gap-2 rounded-[16px] border border-[var(--border-subtle)] p-5">
      <span className="text-[12px] text-[var(--text-secondary)]">{label}</span>
      <span className="text-[24px] font-semibold leading-none [font-variant-numeric:tabular-nums]">{value}</span>
      <span className="text-[12px] text-[var(--text-secondary)]">{note}</span>
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

/** Figma Admin/FilterChip: label and what selecting it would show. */
function Facet({ label, count, on, onClick }: { label: string; count: number; on: boolean; onClick: () => void }) {
  return (
    <button
      type="button"
      aria-pressed={on}
      onClick={onClick}
      className={`inline-flex h-8 items-center gap-1.5 rounded-full border px-3 text-[14px] leading-none ${
        on ? "border-[var(--base-ink-800)] bg-[var(--base-ink-800)] text-white" : "border-[var(--border-subtle)] hover:border-[var(--text-secondary)]"
      }`}
    >
      {label}
      <span className={`text-[12px] ${on ? "text-white/80" : "text-[var(--text-secondary)]"}`}>{count}</span>
    </button>
  );
}

/** The reviewed review, as the overlays draw it at the top. */
function ReviewCard({ review, now, details }: { review: StoreReview; now: number; details: boolean }) {
  return (
    <div className="flex flex-col gap-3 rounded-[16px] border border-[var(--border-subtle)] p-4">
      <div className="flex items-center gap-3">
        <PersonCell name={reviewerName(review)} stage={review.reviewer?.trust_stage ?? null} />
        <span className="flex-1" />
        <StarRow value={review.overall_rating} size={14} />
        <span className="text-[12px] text-[var(--text-secondary)]" suppressHydrationWarning>
          {agoShort(review.created_at, now)}
        </span>
      </div>
      <p className="text-[14px] font-medium">{review.title || "Untitled review"}</p>
      {review.comment ? <p className="text-[14px] leading-[21px] text-[var(--text-secondary)]">{review.comment}</p> : null}
      {details ? (
        <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-[12px] sm:grid-cols-5">
          {[
            ["Matched the listing", review.accuracy ? "Yes" : "No"],
            ["Order complete", review.order_completeness ? "Yes" : "No"],
            ["Customer service", `${review.customer_service ?? "—"} / 5`],
            ["Packaging", `${review.packaging_quality ?? "—"} / 5`],
            ["Would recommend", review.would_recommend ? "Yes" : "No"],
          ].map(([k, v]) => (
            <div key={k} className="flex flex-col gap-0.5">
              <dt className="text-[var(--text-secondary)]">{k}</dt>
              <dd>{v}</dd>
            </div>
          ))}
        </dl>
      ) : null}
    </div>
  );
}

function RespondModal({
  review,
  storeName,
  canFlag,
  onFlag,
  onClose,
  now,
}: {
  review: StoreReview;
  storeName: string;
  canFlag: boolean;
  onFlag: () => void;
  onClose: () => void;
  now: number;
}) {
  const router = useRouter();
  const editing = Boolean(review.seller_response);
  const [body, setBody] = useState(review.seller_response ?? "");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const first = reviewerName(review).split(" ")[0];
  const unchanged = editing && body.trim() === (review.seller_response ?? "").trim();

  async function post() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/sellers/reviews/${review.id}/response`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ body: body.trim() }),
      });
      if (!res.ok) {
        setError(problem(await res.json().catch(() => ({})), "Your response couldn't be posted."));
        setConfirming(false);
        return;
      }
      setConfirming(false);
      onClose();
      router.refresh();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <AdminModal title={editing ? "Edit your response" : `Respond to ${reviewerName(review)}`} width={560} onClose={onClose}>
        <div className="flex flex-col gap-4 overflow-y-auto px-6 pb-5 pt-4">
          <ReviewCard review={review} now={now} details={!editing} />
          <CountedTextarea
            id="store-response"
            label="Your public response"
            value={body}
            onChange={setBody}
            max={MAX}
            rows={5}
            placeholder="Thank the buyer, explain what happened, and say what you'll do next. No links or contact details."
            hint={
              editing && review.seller_response_at
                ? `Posted ${agoShort(review.seller_response_at, now)}${review.seller_response_edited_at ? ` · edited ${agoShort(review.seller_response_edited_at, now)}` : ""}`
                : `Shown under the review as “Response from ${storeName}”`
            }
          />
          <p className="text-[12px] text-[var(--text-secondary)]">
            {editing
              ? "Buyers see your new response in place of the old one."
              : "You can edit your response later. You can't remove or hide a review. If you think it's fake, flag it instead."}
          </p>
          {error ? (
            <p role="alert" className="text-[12px] text-[var(--accent-danger)]">
              {error}
            </p>
          ) : null}
        </div>
        <div className="flex items-center gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
          {canFlag ? (
            <button type="button" onClick={onFlag} className="h-9 rounded-full px-1 text-[12px] text-[var(--status-critical-fg)] underline-offset-4 hover:underline">
              Flag this review
            </button>
          ) : null}
          <span className="flex-1" />
          <button type="button" onClick={onClose} className="h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px]">
            Cancel
          </button>
          <button
            type="button"
            disabled={!body.trim() || countState(body, MAX).over || unchanged || busy}
            onClick={() => setConfirming(true)}
            className="h-9 rounded-full bg-[var(--accent-primary)] px-4 text-[12px] text-white disabled:opacity-50"
          >
            {editing ? "Save changes" : "Post response"}
          </button>
        </div>
      </AdminModal>
      <ConfirmDialog
        open={confirming}
        title={editing ? "Save your edit?" : "Post your response?"}
        confirmLabel={editing ? "Save changes" : "Post response"}
        busyLabel="Saving…"
        busy={busy}
        error={error}
        onConfirm={() => void post()}
        onClose={() => setConfirming(false)}
      >
        {/* Figma Confirm/Store/SaveResponse 8202:22699 and PostResponse 8202:22581. */}
        {editing ? (
          <>
            <p>Your new response replaces the old one.</p>
            <p>Buyers see &ldquo;Edited&rdquo; next to it.</p>
          </>
        ) : (
          <>
            <p>It shows under {first}&rsquo;s review right away.</p>
            <p>{first} is notified.</p>
            <p>You can edit it later.</p>
          </>
        )}
      </ConfirmDialog>
    </>
  );
}

function FlagModal({ review, onClose, now }: { review: StoreReview; onClose: () => void; now: number }) {
  const router = useRouter();
  const [reason, setReason] = useState("");
  const [kind, setKind] = useState<AppealKind>("never_ordered");
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tooShort = reason.trim().length < 10 || countState(reason, MAX).over;
  const chosen = appealKind(kind);

  async function send() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/sellers/reviews/${review.id}/appeal`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ reason: reason.trim(), kind }),
      });
      if (!res.ok) {
        setError(problem(await res.json().catch(() => ({})), "Your flag couldn't be sent."));
        setConfirming(false);
        return;
      }
      setConfirming(false);
      onClose();
      router.refresh();
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <AdminModal title="Flag this review" width={560} onClose={onClose}>
        <div className="flex flex-col gap-4 overflow-y-auto px-6 pb-5 pt-4">
          <ReviewCard review={review} now={now} details={false} />
          {/* MQA-041: say what is wrong, so the admin runs the check that fits. */}
          <fieldset className="flex flex-col gap-2">
            <legend className="pb-2 text-[12px] font-medium uppercase tracking-[0.04em] text-[var(--text-secondary)]">What&rsquo;s wrong with it?</legend>
            {APPEAL_KINDS.map((k) => (
              <label key={k.kind} className={`flex cursor-pointer items-start gap-3 rounded-[12px] border px-3 py-2.5 ${kind === k.kind ? "border-[var(--text-primary)]" : "border-[var(--border-subtle)]"}`}>
                <input type="radio" name="flag-kind" value={k.kind} checked={kind === k.kind} onChange={() => setKind(k.kind)} className="mt-1 accent-[var(--accent-primary)]" />
                <span className="flex min-w-0 flex-col gap-0.5">
                  <span className="text-[14px]">{k.label}</span>
                  <span className="text-[12px] text-[var(--text-secondary)]">{k.hint}</span>
                </span>
              </label>
            ))}
          </fieldset>
          <CountedTextarea
            id="flag-reason"
            label={chosen.prompt}
            value={reason}
            onChange={setReason}
            max={MAX}
            min={10}
            rows={4}
            placeholder={chosen.placeholder}
            hint="Only admins see this. No links. At least 10 characters."
          />
          <div>
            <p className="pb-2 text-[12px] font-medium uppercase tracking-[0.04em] text-[var(--text-secondary)]">What happens next</p>
            <ol className="flex flex-col gap-2 text-[14px]">
              {[
                "An admin checks your flag.",
                chosen.check,
                "Upheld: the review is removed. Dismissed: it stays up and you're told why.",
              ].map((t, i) => (
                <li key={t} className="flex gap-3">
                  <span className="grid size-6 shrink-0 place-items-center rounded-full bg-[var(--surface-app)] text-[12px]">{i + 1}</span>
                  <span>{t}</span>
                </li>
              ))}
            </ol>
          </div>
          {error ? (
            <p role="alert" className="text-[12px] text-[var(--accent-danger)]">
              {error}
            </p>
          ) : null}
        </div>
        <div className="flex items-center gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
          <span className="flex-1 text-[12px] text-[var(--text-secondary)]">You can flag a review once</span>
          <button type="button" onClick={onClose} className="h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px]">
            Cancel
          </button>
          <button
            type="button"
            disabled={tooShort || busy}
            onClick={() => setConfirming(true)}
            className="h-9 rounded-full bg-[var(--accent-primary)] px-4 text-[12px] text-white disabled:opacity-50"
          >
            Send flag
          </button>
        </div>
      </AdminModal>
      <ConfirmDialog
        open={confirming}
        title="Send this flag?"
        confirmLabel="Send flag"
        busyLabel="Sending…"
        busy={busy}
        error={error}
        onConfirm={() => void send()}
        onClose={() => setConfirming(false)}
      >
        {/* Figma Confirm/Store/SendFlag 8202:22623. */}
        <p>An admin checks it. The review stays up meanwhile.</p>
        <p>You can&rsquo;t flag this review again.</p>
        <p>Follow it in Appeals.</p>
      </ConfirmDialog>
    </>
  );
}
