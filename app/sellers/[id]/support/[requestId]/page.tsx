import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CaretLeft } from "@phosphor-icons/react/dist/ssr";

import { categoryLabel, statusLabel } from "@/components/sellers/support-model";
import { SiteFooter } from "@/components/site/SiteFooter";
import { SiteHeader } from "@/components/site/SiteHeader";
import { Unavailable } from "@/components/site/Unavailable";
import { requireOnboardedUser } from "@/lib/dal";
import { getStoreSupportRequest } from "@/lib/support";

export const metadata: Metadata = { title: "Support request — bluntly" };

const WHEN = new Intl.DateTimeFormat("en-PH", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Manila" });

/** One of the store's support requests, as its owner sees it: their words,
 *  the status and the team's last reply — never the staff-only note. A request
 *  moved from Messages is that conversation (MQA-021): "Reply in Messages"
 *  opens it, where the seller answers and attaches proof (MQA-023). */
export default async function SupportRequestPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string; requestId: string }>;
  searchParams: Promise<{ sent?: string }>;
}) {
  const { id, requestId } = await params;
  const { sent } = await searchParams;
  const me = await requireOnboardedUser();
  const result = await getStoreSupportRequest(id, requestId);
  if (!result.ok && result.reason === "not_found") notFound();

  return (
    <div className="flex min-h-dvh flex-col bg-[var(--surface-app)]">
      <SiteHeader user={{ username: me.username, avatarUrl: me.avatar_url, role: me.role }} />
      <main className="mx-auto w-full min-w-0 max-w-[44rem] flex-1 px-4 py-8 md:px-6">
        <Link
          href={`/sellers/${id}/dashboard#support`}
          className="inline-flex items-center gap-1 text-[13px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        >
          <CaretLeft size={16} /> Store dashboard
        </Link>
        {result.ok ? (
          <article className="mt-4">
            {sent === "1" ? (
              <p role="status" className="mb-4 rounded-[12px] bg-[var(--surface-card)] px-4 py-3 text-[13px] shadow-[var(--shadow-hairline-inset)]">
                Sent. An administrator will read it and reply here.
              </p>
            ) : null}
            <p className="text-[12px] text-[var(--text-muted)]">
              {result.data.reference} · {categoryLabel(result.data.category)}
            </p>
            <h1 className="mt-1 text-[22px] font-bold text-[var(--text-primary)] [overflow-wrap:anywhere]">
              {result.data.subject}
            </h1>
            <p className="mt-2 inline-flex rounded-full bg-[var(--surface-card)] px-3 py-1 text-[12px] font-semibold shadow-[var(--shadow-hairline-inset)]" data-testid="support-status">
              {statusLabel(result.data.status)}
            </p>
            {result.data.status === "waiting_for_seller" ? (
              // MQA-022/023: the seller's turn, said plainly, with the way to answer.
              <p role="status" className="mt-4 rounded-[12px] bg-[var(--status-high-bg)] px-4 py-3 text-[14px] text-[var(--status-high-fg)]">
                Action needed: Bluntly asked you for more information. Reply below, and attach any proof there.
              </p>
            ) : null}
            {result.data.conversation_id ? (
              <Link
                href={`/seller/${id}/messages?c=${result.data.conversation_id}`}
                data-testid="support-thread-link"
                className="mt-4 inline-flex h-10 items-center rounded-full bg-[var(--accent-primary)] px-5 text-[14px] font-medium text-white"
              >
                Reply in Messages
              </Link>
            ) : null}
            <section className="mt-6 rounded-[12px] bg-[var(--surface-card)] p-4 shadow-[var(--shadow-card)]">
              <h2 className="text-[13px] font-semibold text-[var(--text-secondary)]">Your message</h2>
              <p className="mt-2 whitespace-pre-line text-[14px] leading-[21px] text-[var(--text-primary)] [overflow-wrap:anywhere]">
                {result.data.message}
              </p>
              <p className="mt-3 text-[11px] text-[var(--text-muted)]">Sent {WHEN.format(new Date(result.data.created_at))}</p>
              {result.data.related_seller_review_id ? (
                <Link
                  href={`/sellers/${id}#review-${result.data.related_seller_review_id}`}
                  className="mt-2 inline-block text-[13px] text-[var(--accent-primary)] hover:underline"
                >
                  The review this is about
                </Link>
              ) : null}
            </section>
            <section className="mt-4 rounded-[12px] bg-[var(--surface-card)] p-4 shadow-[var(--shadow-card)]" aria-label="Bluntly's reply">
              <h2 className="text-[13px] font-semibold text-[var(--text-secondary)]">Bluntly&rsquo;s reply</h2>
              {result.data.admin_response ? (
                <>
                  <p className="mt-2 whitespace-pre-line text-[14px] leading-[21px] text-[var(--text-primary)] [overflow-wrap:anywhere]" data-testid="support-reply">
                    {result.data.admin_response}
                  </p>
                  {result.data.admin_responded_at ? (
                    <p className="mt-3 text-[11px] text-[var(--text-muted)]">
                      {WHEN.format(new Date(result.data.admin_responded_at))}
                    </p>
                  ) : null}
                </>
              ) : (
                <p className="mt-2 text-[14px] text-[var(--text-secondary)]">No reply yet.</p>
              )}
            </section>
          </article>
        ) : result.reason === "forbidden" ? (
          <p className="mt-4 text-[14px] text-[var(--text-secondary)]">
            Only the store&rsquo;s approved owner can see its support requests.
          </p>
        ) : (
          <Unavailable what="this support request" />
        )}
      </main>
      <SiteFooter />
    </div>
  );
}
