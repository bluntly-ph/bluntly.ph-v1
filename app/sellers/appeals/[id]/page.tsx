import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

import { SubstantiationForm } from "@/components/sellers/SubstantiationForm";
import { SiteFooter } from "@/components/site/SiteFooter";
import { SiteHeader } from "@/components/site/SiteHeader";
import { apiFetch } from "@/lib/api/client";
import { requireUser } from "@/lib/dal";
import { getSessionToken } from "@/lib/session";
import type { SellerAppeal } from "@/lib/sellers";

export const metadata: Metadata = { title: "Back up your store review — bluntly" };

/**
 * Where "Please back up your store review" leads (Business Rules §10).
 *
 * A claimed seller flagged this person's review of their store as fake, and an
 * admin has asked them to substantiate it. They see what the store said and
 * what the admin asked, and answer once. Only the review's author can open it;
 * anyone else gets the same not-found as a missing appeal.
 */
export default async function AppealPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const me = await requireUser();
  const appeal = await apiFetch<SellerAppeal>(`/api/v1/sellers/appeals/${id}`, {
    token: await getSessionToken(),
  }).catch(() => null);
  if (!appeal) notFound();

  const awaiting = appeal.status === "substantiation_requested" && !appeal.substantiation_response;

  return (
    <div className="flex min-h-dvh flex-col bg-[var(--surface-app)]">
      <SiteHeader user={{ username: me.username, avatarUrl: me.avatar_url, role: me.role }} />
      <main className="mx-auto w-full max-w-[40rem] flex-1 px-6 py-8">
        <h1 className="text-[20px] font-semibold text-[var(--text-primary)]">Back up your store review</h1>
        <p className="mt-2 text-[13px] leading-[20px] text-[var(--text-secondary)]">
          The store you reviewed believes your review isn&rsquo;t genuine. The store can&rsquo;t remove or
          hide it — an admin decides, and has asked you for anything that shows the order was real.
        </p>

        <section className="mt-6 rounded-[16px] bg-[var(--surface-card)] p-4 shadow-[var(--shadow-card)]">
          <h2 className="text-[13px] font-semibold text-[var(--text-primary)]">What the store said</h2>
          <p className="mt-1 whitespace-pre-line text-[13px] text-[var(--text-secondary)] [overflow-wrap:anywhere]">
            {appeal.reason}
          </p>
          {appeal.substantiation_request ? (
            <>
              <h2 className="mt-4 text-[13px] font-semibold text-[var(--text-primary)]">What the admin asked</h2>
              <p className="mt-1 whitespace-pre-line text-[13px] text-[var(--text-secondary)] [overflow-wrap:anywhere]">
                {appeal.substantiation_request}
              </p>
            </>
          ) : null}
          <p className="mt-4">
            <Link
              href={`/sellers/${appeal.seller_id}#seller-review-${appeal.seller_review_id}`}
              className="text-[13px] text-[var(--accent-primary)] underline-offset-4 hover:underline"
            >
              See your review
            </Link>
          </p>
        </section>

        {awaiting ? (
          <SubstantiationForm appealId={appeal.id} />
        ) : (
          <p role="status" className="mt-6 text-[13px] text-[var(--text-secondary)]">
            {appeal.substantiation_response
              ? "You've answered. An admin will decide, and you'll be told the outcome."
              : appeal.status === "open"
                ? "Nothing is being asked of you yet."
                : appeal.status === "dismissed"
                  ? "The appeal was dismissed. Your review stays up."
                  : appeal.status === "upheld"
                    ? "The appeal was upheld and your review was removed."
                    : "Nothing is being asked of you right now."}
          </p>
        )}
      </main>
      <SiteFooter />
    </div>
  );
}
