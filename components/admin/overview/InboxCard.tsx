import Link from "next/link";

import { OVERVIEW_CARD, OverviewCardHeader } from "@/components/admin/overview/OverviewCardHeader";
import { initials } from "@/components/admin/overview/overview-model";
import { Chip } from "@/components/console/Chip";
import { TOPIC_LABEL, agoCompact, firstName } from "@/components/messages/messages-model";
import type { ConversationRow } from "@/lib/messages";

/**
 * "Inbox" (Card/Inbox 8444:38777, Screen/Admin/Overview v4, read 2026-10-05):
 * the three conversations that have waited on the team longest, and how many
 * are waiting in all (GET /admin/inbox?status=open&sort=waiting — "open" is
 * the ball in our court; "waiting" is waiting on them).
 *
 * Row: a 36px initials avatar (a seller's in the brand tint and orange, a
 * reviewer's in gray-200), the name in 14px Medium with a Seller (neutral) or
 * Reviewer (muted) chip, under it "Topic · “preview”" in 12px at 40% on one
 * line; on the right the age in 12px Medium at 70% and who has it — the
 * assignee's first name at 40%, or "Unassigned" in critical red.
 */
export function InboxCard({
  data,
  now,
}: {
  data: { items: ConversationRow[]; total: number } | null;
  now: number;
}) {
  return (
    <section aria-labelledby="inbox-card-heading" className={OVERVIEW_CARD}>
      <OverviewCardHeader
        id="inbox-card-heading"
        title="Inbox"
        href="/admin/inbox?status=open&sort=waiting"
        note={data ? `${data.total} waiting on us` : null}
      />
      {data === null ? (
        <p role="status" className="text-[13px] text-[var(--text-secondary)]">
          The inbox could not be loaded. It is still reachable from the rail.
        </p>
      ) : data.items.length === 0 ? (
        <p className="py-2 text-[13px] text-[var(--text-secondary)]">Nothing is waiting on the team.</p>
      ) : (
        <ul className="flex flex-col">
          {data.items.map((c) => {
            const seller = c.audience === "seller";
            const name = (seller ? c.seller_name : null) ?? c.member?.name ?? "Member";
            const topic = TOPIC_LABEL[c.topic] ?? "General";
            const line = c.preview ? `${topic} · “${c.preview}”` : `${topic} · ${c.subject}`;
            return (
              <li key={c.id}>
                <Link
                  href={`/admin/inbox?c=${c.id}`}
                  className="flex min-w-0 items-center gap-3 rounded-[8px] py-2 hover:bg-[var(--surface-app)]"
                >
                  <span
                    aria-hidden="true"
                    className={`grid size-9 shrink-0 place-items-center rounded-full text-[12px] font-medium leading-4 ${
                      seller
                        ? "bg-[rgba(239,88,33,0.1)] text-[var(--accent-primary)]"
                        : "bg-[var(--base-gray-200)] text-[var(--text-secondary)]"
                    }`}
                  >
                    {initials(name)}
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col gap-1">
                    <span className="flex min-w-0 items-center gap-1.5">
                      <span className="min-w-0 truncate text-[14px] font-medium leading-5">{name}</span>
                      <Chip tone={seller ? "neutral" : "muted"}>{seller ? "Seller" : "Reviewer"}</Chip>
                    </span>
                    <span className="truncate text-[12px] leading-4 text-[var(--text-muted)]">{line}</span>
                  </span>
                  <span className="flex shrink-0 flex-col items-end gap-1 text-[12px] leading-4">
                    <span className="font-medium text-[var(--text-secondary)]">{agoCompact(c.last_message_at, now)}</span>
                    {c.assigned_admin ? (
                      <span className="text-[var(--text-muted)]">{firstName(c.assigned_admin.name)}</span>
                    ) : (
                      <span className="text-[var(--status-critical-fg)]">Unassigned</span>
                    )}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
