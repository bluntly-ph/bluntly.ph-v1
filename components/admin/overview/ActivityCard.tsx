import Link from "next/link";

import { activitySentence } from "@/components/admin/activity/activity-words";
import { OVERVIEW_CARD, OverviewCardHeader } from "@/components/admin/overview/OverviewCardHeader";
import { initials } from "@/components/admin/overview/overview-model";
import { agoCompact } from "@/components/messages/messages-model";
import type { ActivityEntry } from "@/lib/activity-admin";

/**
 * "Recent team activity" (Card/Activity 8444:38818, Screen/Admin/Overview v4,
 * read 2026-10-05): the five newest Activity log entries (GET /admin/activity),
 * worded exactly as the log words them (activity-words). Row: a 28px gray
 * initials avatar, the sentence in 14px Regular on one line, the age in 12px
 * at 40%. "Activity log" on the right of the header opens the log.
 */
export function ActivityCard({ rows, now }: { rows: ActivityEntry[] | null; now: number }) {
  return (
    <section aria-labelledby="activity-card-heading" className={OVERVIEW_CARD}>
      <OverviewCardHeader
        id="activity-card-heading"
        title="Recent team activity"
        href="/admin/activity"
        note={
          <Link href="/admin/activity" className="hover:text-[var(--accent-primary)]">
            Activity log
          </Link>
        }
      />
      {rows === null ? (
        <p role="status" className="text-[13px] text-[var(--text-secondary)]">
          The activity log could not be loaded.
        </p>
      ) : rows.length === 0 ? (
        <p className="py-2 text-[13px] text-[var(--text-secondary)]">No team activity yet.</p>
      ) : (
        <ul className="flex flex-col">
          {rows.map((e) => {
            const text = activitySentence(e);
            const body = (
              <>
                <span
                  aria-hidden="true"
                  className="grid size-7 shrink-0 place-items-center rounded-full bg-[var(--base-gray-200)] text-[12px] font-medium leading-4 text-[var(--text-secondary)]"
                >
                  {initials(e.actor ?? "System")}
                </span>
                <span className="min-w-0 flex-1 truncate text-[14px] leading-5" title={text}>
                  {text}
                </span>
                <time dateTime={e.at} className="shrink-0 text-[12px] leading-4 text-[var(--text-muted)]">
                  {agoCompact(e.at, now)}
                </time>
              </>
            );
            return (
              <li key={e.id}>
                {e.href ? (
                  <Link href={e.href} className="flex min-w-0 items-center gap-3 rounded-[8px] py-[7px] hover:bg-[var(--surface-app)]">
                    {body}
                  </Link>
                ) : (
                  <div className="flex min-w-0 items-center gap-3 py-[7px]">{body}</div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
