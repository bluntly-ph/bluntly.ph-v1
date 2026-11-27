"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";
import { Star } from "@phosphor-icons/react/dist/ssr";

import { AdminModal } from "@/components/admin/AdminModal";
import { DESTINATIONS, oldest, routedThisMonth, waiting, type Destination } from "@/components/admin/routing/routing-model";
import { Chip } from "@/components/console/Chip";
import { CountedTextarea } from "@/components/console/CountedTextarea";
import { countState } from "@/components/console/counted-model";
import { Pagination } from "@/components/console/Pagination";
import { PAGE_SIZES } from "@/components/console/pagination-model";
import { ProductThumbnail } from "@/components/console/ProductThumbnail";
import type { SpecialRoutingDecision, SpecialRoutingItem } from "@/lib/special-routing";

export type { Destination };

export const DESTINATION_LABEL: Record<Destination, string> = {
  honesty_fund: "Honesty Fund",
  platform: "Platform",
};

const WHEN = new Intl.DateTimeFormat("en-PH", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Manila" });
const DAY = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", timeZone: "Asia/Manila" });
const NOTE_MAX = 500;

/**
 * Screen/Admin/SpecialRouting (Figma 8178:20045) and Overlay/Routing/Track
 * (8178:20344): the 2.5-star "It depends" earnings track (owner decision A,
 * 2026-09-28). An Administrator approved each to earn; where the money goes is
 * the Super Admin's call, and exactly one of two (Honesty Fund or Platform —
 * the frame's "Commission" option is not a destination the rules have). The
 * API records who decided and refuses a second, different decision (409
 * already_routed).
 *
 * The frame's "Escalated reports" tab is a link to where those reports are
 * decided: Queue › Reports › Escalated (MQA-005), with its live count.
 *
 * Not drawn: "Escalated reviews" (nothing escalates a review other than a
 * report on it, which is the tab before) and "Set a rule" with the overlay's
 * "Use this for every…" switch (routing has no rules), so those would be empty
 * shells.
 */
export function SpecialRoutingQueue({
  items,
  history,
  now,
  escalatedReports = null,
}: {
  items: SpecialRoutingItem[] | null;
  history: SpecialRoutingDecision[] | null;
  now: number;
  /** Reports escalated to a Super Admin (null when the count could not be read). */
  escalatedReports?: number | null;
}) {
  const router = useRouter();
  const [open, setOpen] = useState<SpecialRoutingItem | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [paging, setPaging] = useState({ page: 1, size: PAGE_SIZES[0] as number });

  const list = items ?? [];
  const first = oldest(list);
  const firstWait = first ? waiting(first.escalated_at ?? first.created_at, now) : null;
  const month = routedThisMonth(history ?? [], now);
  const rows = list.slice((paging.page - 1) * paging.size, paging.page * paging.size);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-center gap-3">
        <nav aria-label="Routing views" className="flex w-fit gap-[2px] rounded-[10px] bg-[var(--surface-app)] p-[3px]">
          <span aria-current="page" className="flex items-center gap-[6px] rounded-[8px] bg-[var(--surface-card)] px-3 py-[5px] leading-none shadow-[var(--shadow-segment)]">
            <span className="text-[14px] font-medium">Earnings track</span>
            <span className="text-[12px] text-[var(--text-secondary)]">{items ? list.length : "—"}</span>
          </span>
          <Link
            href="/admin/review-queue?tab=reports&rstatus=escalated"
            className="flex items-center gap-[6px] rounded-[8px] px-3 py-[5px] leading-none text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          >
            <span className="text-[14px]">Escalated reports</span>
            <span className="text-[12px]">{escalatedReports ?? "—"}</span>
          </Link>
        </nav>
      </div>

      <div aria-live="polite" className="empty:hidden">
        {notice ? (
          <p role="status" className="text-[13px] text-[var(--accent-success)]">
            {notice}
          </p>
        ) : null}
      </div>

      <section aria-label="The routing queue in numbers" className="grid grid-cols-[minmax(0,1fr)] gap-3 sm:grid-cols-3">
        <Stat label="Waiting" value={items ? String(list.length) : "—"} />
        <Stat
          label="Oldest"
          value={firstWait ? firstWait.label : "—"}
          note={first ? `${first.product_name ?? first.title} · since ${DAY.format(new Date(first.escalated_at ?? first.created_at))}` : undefined}
        />
        <Stat label="Routed this month" value={history ? String(month.count) : "—"} note={month.by ?? undefined} />
      </section>

      <div className="overflow-x-auto rounded-[16px] border border-[var(--border-subtle)]">
        <table className="w-full min-w-[880px] border-collapse text-left text-[14px]" data-testid="routing-queue">
          <caption className="sr-only">Reviews waiting on a Super Admin</caption>
          <thead className="bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
            <tr>
              {["Review", "Type", "Stars", "Waiting", "Moderator note", "Action"].map((h) => (
                <th key={h} scope="col" className="h-10 px-3 font-normal">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items === null ? (
              <tr>
                <td colSpan={6} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">
                  The queue couldn&rsquo;t be loaded. The API did not answer; this is not an empty queue.
                </td>
              </tr>
            ) : list.length === 0 ? (
              <tr>
                <td colSpan={6} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">
                  Nothing is waiting on you.
                </td>
              </tr>
            ) : (
              rows.map((item) => {
                const w = waiting(item.escalated_at ?? item.created_at, now);
                return (
                  <tr key={item.review_id} className="group border-t border-[var(--border-subtle)] hover:bg-[var(--surface-app)]">
                    <td className="max-w-[300px] px-3 py-[10px]">
                      <span className="flex items-center gap-3">
                        <ProductThumbnail url={item.product_image_url} />
                        <span className="flex min-w-0 flex-col gap-1 leading-4 [&>:first-child]:leading-5">
                          <Link href={`/reviews/${item.review_id}`} className="truncate hover:underline">
                            {item.product_name ?? item.title}
                          </Link>
                          <span className="truncate text-[12px] text-[var(--text-secondary)]">by {item.author_name ?? item.author ?? "a former member"}</span>
                        </span>
                      </span>
                    </td>
                    <td className="px-3">Review</td>
                    <td className="whitespace-nowrap px-3">
                      <span className="inline-flex items-center gap-1">
                        <Star size={16} weight="fill" className="text-[var(--accent-star)]" aria-hidden />
                        {Number(item.stars).toFixed(1)}
                      </span>
                    </td>
                    <td className={`whitespace-nowrap px-3 ${w.late ? "text-[var(--status-high-fg)]" : ""}`} suppressHydrationWarning>
                      {w.label}
                    </td>
                    <td className="max-w-[260px] px-3 text-[12px] text-[var(--text-secondary)]">
                      <span className="line-clamp-2">{item.approval_note ?? "—"}</span>
                    </td>
                    <td className="px-3">
                      <button
                        type="button"
                        onClick={() => {
                          setNotice(null);
                          setOpen(item);
                        }}
                        aria-label={`Route ${item.title}`}
                        className="h-8 rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 text-[12px] hover:border-[var(--text-secondary)]"
                      >
                        Route
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      {items && list.length > 0 ? (
        <Pagination page={paging.page} size={paging.size} total={list.length} onChange={setPaging} label="Routing pages" />
      ) : null}

      <section aria-labelledby="routing-history-heading" className="rounded-[16px] border border-[var(--border-subtle)]">
        <h2 id="routing-history-heading" className="px-4 py-3 text-[14px] font-semibold">
          Recent decisions
        </h2>
        {history === null ? (
          <p className="border-t border-[var(--border-subtle)] px-4 py-6 text-[13px] text-[var(--text-secondary)]">The history couldn&rsquo;t be loaded.</p>
        ) : history.length === 0 ? (
          <p className="border-t border-[var(--border-subtle)] px-4 py-6 text-[13px] text-[var(--text-secondary)]">No decisions yet.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[34rem] text-left text-[13px]" data-testid="routing-history">
              <thead className="bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
                <tr>
                  {["When", "Review", "Routed to", "By"].map((h) => (
                    <th key={h} scope="col" className="h-9 px-4 font-normal">
                      {h}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {history.slice(0, 10).map((h, i) => (
                  <tr key={`${h.review_id}-${i}`} className="border-t border-[var(--border-subtle)]">
                    <td className="whitespace-nowrap px-4 py-2 text-[var(--text-secondary)]">{WHEN.format(new Date(h.at))}</td>
                    <td className="px-4 py-2">
                      {h.review_id ? (
                        <Link href={`/reviews/${h.review_id}`} className="hover:underline">
                          {h.review_ref ?? h.review_id}
                        </Link>
                      ) : (
                        "—"
                      )}
                    </td>
                    <td className="px-4 py-2 font-medium">{h.destination ? DESTINATION_LABEL[h.destination] : "—"}</td>
                    <td className="px-4 py-2 text-[var(--text-secondary)]">{h.actor_name ?? h.actor_staff_ref ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {open ? (
        <RouteModal
          key={open.review_id}
          item={open}
          now={now}
          onClose={() => setOpen(null)}
          onRouted={(destination) => {
            setNotice(`“${open.title}” routed to ${DESTINATION_LABEL[destination]}.`);
            setOpen(null);
            router.refresh();
          }}
        />
      ) : null}
    </div>
  );
}

function Stat({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <div className="flex flex-col gap-2 rounded-[16px] border border-[var(--border-subtle)] p-5">
      <span className="text-[12px] text-[var(--text-secondary)]">{label}</span>
      <span className="text-[24px] font-semibold leading-none [font-variant-numeric:tabular-nums]" suppressHydrationWarning>
        {value}
      </span>
      {note ? <span className="truncate text-[12px] text-[var(--text-secondary)]">{note}</span> : null}
    </div>
  );
}

/** Overlay/Routing/Track (8178:20344): what the review is, why it's here, the two routes, a note for the log. */
function RouteModal({
  item,
  now,
  onClose,
  onRouted,
}: {
  item: SpecialRoutingItem;
  now: number;
  onClose: () => void;
  onRouted: (destination: Destination) => void;
}) {
  const [destination, setDestination] = useState<Destination | null>(null);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const noteOver = countState(note, NOTE_MAX).over;
  const posted = waiting(item.created_at, now);

  async function route() {
    if (!destination || noteOver) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/bff/api/v1/admin/super/special-routing/${encodeURIComponent(item.review_id)}`, {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ destination, confirm: "route", note: note.trim() || null }),
      });
      if (!res.ok) {
        const p = (await res.json().catch(() => ({}))) as { detail?: string };
        setError(typeof p.detail === "string" ? p.detail : "That didn't go through.");
        return;
      }
      onRouted(destination);
    } catch {
      setError("Couldn't reach the server.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <AdminModal title="Route earnings" width={560} onClose={() => (busy ? undefined : onClose())}>
      <div className="flex flex-col gap-5 p-6 text-[14px]">
        <div className="flex flex-col gap-3">
          <div className="flex items-center gap-3">
            <ProductThumbnail url={item.product_image_url} size={40} />
            <span className="flex min-w-0 flex-1 flex-col gap-1 leading-none">
              <span className="truncate font-medium">{item.product_name ?? item.title}</span>
              <span className="truncate text-[12px] text-[var(--text-secondary)]" suppressHydrationWarning>
                by {item.author_name ?? item.author ?? "a former member"} · posted {posted.label} ago
              </span>
            </span>
            <span className="inline-flex items-center gap-1 text-[16px] font-semibold">
              <Star size={18} weight="fill" className="text-[var(--accent-star)]" aria-hidden />
              {Number(item.stars).toFixed(1)}
            </span>
          </div>
          <p className="font-medium">{item.title}</p>
          {item.excerpt ? <p className="text-[var(--text-secondary)]">&ldquo;{item.excerpt}&rdquo;</p> : null}
          <div className="flex flex-wrap gap-2">
            <Chip>Verdict · It depends</Chip>
            <Chip>{item.photo_provided ? "Photo provided" : "No photo"}</Chip>
            {item.approval_note ? <Chip tone="muted">Approved to earn</Chip> : null}
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <p className="text-[12px] font-medium uppercase tracking-[0.04em] text-[var(--text-secondary)]">Why it&rsquo;s here</p>
          <p>
            The verdict leaves the track to the stars: 3 stars or more earns commission, 2 or less goes to the Honesty Fund. 2.5 sits between them,
            so a Super Admin decides. Sales that arrive before you decide are held, not credited.
          </p>
        </div>

        <fieldset className="flex flex-col gap-2">
          <legend className="mb-2 text-[12px] font-medium uppercase tracking-[0.04em] text-[var(--text-secondary)]">Route to</legend>
          {DESTINATIONS.map((d) => (
            <label
              key={d.key}
              className={`flex cursor-pointer items-start gap-3 rounded-[12px] border p-4 ${destination === d.key ? "border-[var(--accent-primary)]" : "border-[var(--border-subtle)] hover:border-[var(--border-input-hover)]"}`}
            >
              <input type="radio" name="destination" value={d.key} checked={destination === d.key} onChange={() => setDestination(d.key)} className="mt-1 accent-[var(--accent-primary)]" />
              <span className="flex min-w-0 flex-1 flex-col gap-2">
                <span className="font-medium">{d.label}</span>
                <span className="text-[12px] text-[var(--text-secondary)]">{d.meaning}</span>
                <span className="flex h-[6px] overflow-hidden rounded-full" aria-hidden>
                  {d.split.map(([who, pct], i) => (
                    <span key={who} style={{ width: `${pct}%` }} className={i === 0 ? "bg-[var(--accent-primary)]" : "bg-[var(--status-baseline-fg)]"} />
                  ))}
                </span>
                <span className="flex gap-3 text-[12px] text-[var(--text-secondary)]">
                  {d.split.map(([who, pct]) => (
                    <span key={who}>
                      {who} {pct}
                    </span>
                  ))}
                </span>
              </span>
            </label>
          ))}
        </fieldset>

        <CountedTextarea id="route-note" label="Note for the log" value={note} onChange={setNote} max={NOTE_MAX} rows={2} placeholder="Optional. Why this track?" />

        {error ? (
          <p role="alert" className="text-[12px] text-[var(--accent-danger)]">
            {error}
          </p>
        ) : null}
      </div>
      <div className="flex flex-wrap items-center gap-3 border-t border-[var(--border-subtle)] px-6 py-4">
        <span className="flex-1 text-[12px] text-[var(--text-secondary)]">Final, and logged in the Activity log. The author is told.</span>
        <button type="button" onClick={onClose} disabled={busy} className="h-9 rounded-full border border-[var(--text-primary)] px-4 text-[12px]">
          Cancel
        </button>
        <button
          type="button"
          onClick={() => void route()}
          disabled={!destination || noteOver || busy}
          className="h-9 rounded-full bg-[var(--accent-primary)] px-4 text-[12px] font-medium text-[var(--text-on-brand)] disabled:bg-[var(--disabled-surface)] disabled:text-[var(--disabled-text)]"
        >
          {busy ? "Routing…" : destination ? `Route to ${DESTINATION_LABEL[destination]}` : "Choose a route"}
        </button>
      </div>
    </AdminModal>
  );
}
