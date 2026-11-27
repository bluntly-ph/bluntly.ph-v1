import Link from "next/link";

import { AttachAffiliateForm } from "@/components/admin/AttachAffiliateForm";
import type { AwaitingAffiliateItem } from "@/lib/moderation";

/**
 * Earnings approved, affiliate link missing. Raw engagement facts beside each
 * row — no HIGH/LOW label: which of these deserves a link first is the admin's
 * call, and a formal priority rule is still pending.
 */
export function AwaitingLinks({ data }: { data: { items: AwaitingAffiliateItem[]; total: number } | null }) {
  if (!data) return null;
  return (
    <section className="rounded-[var(--radius-md)] bg-[var(--surface-card)] p-4 shadow-[var(--shadow-card)]">
      <h3 className="text-[14px] font-semibold text-[var(--text-primary)]">
        Awaiting affiliate link{data.total ? ` (${data.total})` : ""}
      </h3>
      <p className="mt-1 text-[12px] text-[var(--text-secondary)]">
        Public reviews an administrator has approved to earn, on a marketplace we can monetize, with no
        link attached yet.
      </p>
      {data.items.length === 0 ? (
        <p className="mt-3 text-[12px] text-[var(--text-muted)]">Nothing is waiting for a link.</p>
      ) : (
        <ul className="mt-3 flex flex-col divide-y divide-[var(--line-hairline-10)]">
          {data.items.map((item) => {
            const d = item.momentum.last_24h;
            const w = item.momentum.last_7d;
            const markets = item.platforms.filter((p) => p.is_monetizable).map((p) => p.platform);
            return (
              <li key={item.review.id} className="flex flex-col gap-2 py-3">
                <div className="flex flex-wrap items-baseline justify-between gap-2">
                  <Link
                    href={`/reviews/${item.review.id}`}
                    className="text-[13px] font-medium text-[var(--text-primary)] hover:text-[var(--accent-primary)]"
                  >
                    {item.review.title}
                  </Link>
                  <span className="text-[11px] text-[var(--text-muted)]">
                    {item.product.canonical_name ?? "Unknown product"} · {markets.join(", ") || "no monetizable listing"}
                  </span>
                </div>
                <p className="text-[11px] text-[var(--text-secondary)]">
                  24h: {d.opens} opens · {d.upvotes} up · {d.downvotes} down · {d.comments} comments
                  {" — "}
                  7d: {w.opens} opens · {w.upvotes} up · {w.downvotes} down · {w.comments} comments ·{" "}
                  {w.participants} participants
                  {item.momentum.open_reports ? ` · ${item.momentum.open_reports} open reports` : ""}
                </p>
                <AttachAffiliateForm
                  reviewId={item.review.id}
                  platforms={markets}
                  suggestedPlatform={item.suggested_platform}
                  subId={item.suggested_sub_id}
                />
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
