"use client";

import Image from "next/image";
import Link from "next/link";
import { useState } from "react";
import { CaretRight, Package } from "@phosphor-icons/react/dist/ssr";

import type { QueuePreviewTab } from "@/lib/moderation";

/**
 * "Review queue" (Card/ReviewQueue 7888:10384): four tabs and, under each, its
 * five most urgent cards (GET /admin/analytics/queue-preview). The tabs
 * overlap by design: one review can be earn eligible and a first review.
 *
 * Ages are measured from when the review entered the queue to `now` (the
 * server's fetch time, so the server and client renders agree), red once its
 * SLA is overdue — the frame's red "3d" against a grey "20h".
 */

function age(iso: string, now: number): string {
  const minutes = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60000));
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.round(hours / 24)}d`;
}

export function ReviewQueueCard({ tabs, now }: { tabs: QueuePreviewTab[] | null; now: number }) {
  const [active, setActive] = useState(0);
  const tab = tabs?.[active];

  return (
    <section
      aria-labelledby="queue-card-heading"
      className="flex min-w-0 flex-col gap-[10px] rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)] p-5"
    >
      <h2 id="queue-card-heading" className="text-[16px] font-semibold leading-none">
        <Link href="/admin/review-queue" className="inline-flex items-center gap-1 hover:text-[var(--accent-primary)]">
          Review queue
          <CaretRight size={14} className="text-[var(--text-secondary)]" />
        </Link>
      </h2>

      {tabs === null ? (
        <p role="status" className="text-[13px] text-[var(--text-secondary)]">
          The queue preview could not be loaded. The queue itself is one click away.
        </p>
      ) : (
        <>
          <div role="tablist" className="flex justify-between gap-2 border-b border-[var(--border-subtle)]">
            {tabs.map((t, i) => (
              <button
                key={t.key}
                type="button"
                role="tab"
                aria-selected={i === active}
                onClick={() => setActive(i)}
                className={`-mb-px flex items-center gap-[5px] whitespace-nowrap border-b-2 pb-[9px] pt-1 text-[12px] font-medium leading-none ${
                  i === active
                    ? "border-[var(--text-primary)] text-[var(--text-primary)]"
                    : "border-transparent text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                }`}
              >
                {t.label}
                <span>{t.count}</span>
              </button>
            ))}
          </div>

          {tab && tab.items.length > 0 ? (
            <ul role="tabpanel">
              {tab.items.map((item, i) => {
                const overdue = item.sla_state === "overdue";
                return (
                  <li key={item.review_id} className={i > 0 ? "border-t border-[var(--border-subtle)]" : ""}>
                    <Link
                      href={`/admin/review-queue?open=${item.review_id}`}
                      className="flex items-center gap-3 py-[7px] hover:bg-[var(--surface-app)]/60 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
                    >
                      <span className="relative grid size-9 shrink-0 place-items-center overflow-hidden rounded-[8px] bg-[var(--surface-app)]">
                        {item.image_url ? (
                          <Image src={item.image_url} alt="" fill sizes="36px" className="object-cover" />
                        ) : (
                          <Package size={18} className="text-[var(--text-muted)]" aria-hidden />
                        )}
                      </span>
                      <span className="flex min-w-0 flex-1 flex-col gap-2 leading-none">
                        <span className="truncate text-[14px] font-medium">
                          {item.product_name ?? "Product not named yet"}
                        </span>
                        <span className="truncate text-[12px] text-[var(--text-secondary)]">
                          {item.author_name ?? "Former member"} · {item.star_rating}★
                        </span>
                      </span>
                      <span
                        className={`text-[12px] font-medium leading-none ${
                          overdue ? "text-[var(--status-critical-fg)]" : "text-[var(--text-secondary)]"
                        }`}
                        title={overdue ? "Past its review deadline" : "Time in the queue"}
                      >
                        {age(item.entered_at, now)}
                      </span>
                      <CaretRight size={14} className="text-[var(--text-secondary)]" />
                    </Link>
                  </li>
                );
              })}
            </ul>
          ) : (
            <p className="py-6 text-center text-[13px] text-[var(--text-secondary)]">
              Nothing waiting in {tab?.label.toLowerCase() ?? "this tab"}.
            </p>
          )}
        </>
      )}
    </section>
  );
}
