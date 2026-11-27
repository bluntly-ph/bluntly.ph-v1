import Link from "next/link";

import { Chip } from "@/components/console/Chip";
import { categoryLabel, isOpen, statusLabel } from "@/components/sellers/support-model";
import type { SupportRequest } from "@/lib/support";

/**
 * The store's requests to the administrators (owner decision 2026-09-28). New
 * ones start as a message to the team (owner decision 2026-10-03: Messages
 * replace the request form; an administrator can still move a conversation to
 * Queue → Support), so "New message" opens Overlay/Store/Chat/New. Requests
 * filed before stay listed here with their own pages.
 */
export function SupportRequestsCard({ storeId, requests }: { storeId: string; requests: SupportRequest[] | null }) {
  return (
    <section id="support" aria-labelledby="support-h" className="flex scroll-mt-4 flex-col gap-3">
      <div className="flex items-center gap-3">
        <h2 id="support-h" className="flex-1 text-[16px] font-semibold leading-none">
          Requests to the administrators
        </h2>
        <Link
          href={`/seller/${storeId}/messages?new=1`}
          className="h-8 rounded-full border border-[var(--text-primary)] px-3 text-[12px] leading-8"
        >
          New message
        </Link>
      </div>
      {requests === null ? (
        <p className="text-[14px] text-[var(--text-secondary)]">Your requests could not be loaded right now.</p>
      ) : requests.length === 0 ? (
        <p className="text-[14px] text-[var(--text-secondary)]">
          No requests yet. To ask about a review, a takedown, your claim or a listing, send the team a message.
        </p>
      ) : (
        <ul className="flex flex-col rounded-[16px] border border-[var(--border-subtle)]">
          {requests.slice(0, 5).map((r) => (
            <li key={r.id} className="flex items-center gap-3 border-t border-[var(--border-subtle)] px-4 py-3 first:border-t-0">
              <Link href={`/sellers/${storeId}/support/${r.id}`} className="flex min-w-0 flex-1 flex-col gap-1 leading-none hover:underline">
                <span className="truncate text-[14px]">{r.subject}</span>
                <span className="truncate text-[12px] text-[var(--text-secondary)]">
                  {r.reference} · {categoryLabel(r.category)}
                </span>
              </Link>
              <Chip tone={isOpen(r.status) ? "warning" : r.status === "resolved" ? "success" : "muted"}>{statusLabel(r.status)}</Chip>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
