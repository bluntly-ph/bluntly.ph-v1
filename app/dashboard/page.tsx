import Link from "next/link";
import type { Metadata } from "next";

import { ContributorDashboard } from "@/components/dashboard/ContributorDashboard";
import { DashboardNav } from "@/components/dashboard/DashboardScreen";
import { AnswersPanel } from "@/components/dashboard/ReviewerDashboard";
import { ScrollToHash } from "@/components/dashboard/ScrollToHash";
import { QuickActions } from "@/components/site/QuickActions";
import { SiteFooter } from "@/components/site/SiteFooter";
import { SiteHeader } from "@/components/site/SiteHeader";
import { Button } from "@/components/ui/Button";
import { requireOnboardedUser } from "@/lib/dal";
import { getContributorDashboard, getDashboard, getMyQuestions, peso } from "@/lib/dashboard";
import { trustLevel } from "@/lib/trust";
import { getMyUnread } from "@/lib/messages";

export const metadata: Metadata = {
  title: "Dashboard — bluntly",
};

const STATUS_STYLE: Record<string, string> = {
  paid: "text-[var(--accent-success)]",
  processing: "text-[var(--accent-star)]",
  scheduled: "text-[var(--text-secondary)]",
  failed: "text-[var(--accent-danger)]",
  cancelled: "text-[var(--text-muted)]",
};

/** Why a payout sits in each state, in the reviewer's words rather than the scheduler's. */
const STATUS_NOTE: Record<string, string> = {
  scheduled: "Reserved from your wallet, waiting to be sent.",
  processing: "Being sent now.",
  paid: "Sent to your payout account.",
  failed: "Didn't go through. The amount was returned to your wallet.",
  cancelled: "Called off. The amount was returned to your wallet.",
};

/**
 * The contributor dashboard, built to Figma Screen/Dashboard (7833:9534;
 * meeting 2026-10-02, 3:00-5:20): Payout / History / Performance, the wallet,
 * earnings, the trust stage and reach — `ContributorDashboard`, on
 * GET /users/me/contributor.
 *
 * Kept below it, because other screens link here: Payment history (#history,
 * History's "Historical Bill") and the answers to your questions
 * (`?tab=answers`, owner round 4).
 */
export default async function DashboardPage({
  searchParams,
}: {
  searchParams: Promise<{ period?: string; reach?: string; tab?: string }>;
}) {
  const me = await requireOnboardedUser();
  const params = await searchParams;
  const answersTab = params.tab === "answers";
  const [data, { payouts }, answers, unread] = await Promise.all([
    getContributorDashboard(params.period ?? "week", params.reach ?? "this"),
    getDashboard(),
    answersTab ? getMyQuestions() : Promise.resolve(null),
    getMyUnread(),
  ]);

  return (
    <div className="flex min-h-dvh flex-col bg-[var(--surface-card)]">
      {/* The frame carries its own bar (back arrow + trust pill); the site
          header returns from `md`, where the frame stops describing the page. */}
      <div className="hidden md:block">
        <SiteHeader user={{ username: me.username, avatarUrl: me.avatar_url, role: me.role }} />
      </div>
      <div className="md:hidden">
        <DashboardNav backHref="/profile" trustLevel={trustLevel(me.trust_level_name, me.trust_stage)} tone="light" unread={unread} />
      </div>

      <main className="flex-1">
        <h1 className="sr-only">Your dashboard</h1>
        <ContributorDashboard data={data} />

        <div className="mx-auto w-full max-w-[390px] px-4 pb-10 md:max-w-[880px] md:px-6">
          <nav aria-label="Your contributions" className="flex flex-wrap gap-x-5 gap-y-2 text-[13px] font-semibold">
            <Link href="/dashboard/reviews" className="text-[var(--accent-primary)] hover:underline">
              Your reviews
            </Link>
            <Link href="/dashboard?tab=answers" aria-current={answersTab ? "page" : undefined} className="text-[var(--accent-primary)] hover:underline">
              Answers
            </Link>
          </nav>
          {answersTab ? (
            <div className="mt-4 rounded-[32px] bg-[var(--surface-app)] p-[3px]">
              <AnswersPanel answers={answers} />
            </div>
          ) : null}

          <section id="history" className="mt-6 scroll-mt-6">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="text-[16px] font-semibold text-[var(--text-primary)]">
              Payment history
            </h2>
            {/* Report 4: the full statement for any month, with CSV and print. */}
            <Link
              href="/dashboard/statement"
              className="text-[13px] font-semibold text-[var(--accent-primary)] hover:underline"
            >
              Earnings statement
            </Link>
          </div>
          <ul className="mt-3 flex flex-col divide-y divide-[var(--border-subtle)] rounded-[var(--radius-sm)] bg-[var(--surface-card)] px-4 shadow-[var(--shadow-hairline-inset)]">
            {payouts.length > 0 ? (
              payouts.map((p) => (
                <li
                  key={p.id}
                  className="flex flex-wrap items-center justify-between gap-x-3 gap-y-1 py-3"
                >
                  <div className="min-w-0">
                    <p className="text-[14px] font-semibold text-[var(--text-primary)]">
                      {peso(p.amount)}
                      <span className="ml-1.5 text-[12px] font-normal text-[var(--text-muted)]">
                        {p.currency}
                      </span>
                    </p>
                    <p className="text-[12px] text-[var(--text-muted)]">
                      {STATUS_NOTE[p.status] ?? ""}
                    </p>
                  </div>
                  <div className="text-right">
                    <span
                      className={`text-[12px] font-medium capitalize ${STATUS_STYLE[p.status] ?? "text-[var(--text-secondary)]"}`}
                    >
                      {p.status}
                    </span>
                    <p className="text-[12px] text-[var(--text-muted)]">
                      {new Date(p.paid_at ?? p.scheduled_for).toLocaleDateString(
                        "en-PH",
                        { year: "numeric", month: "short", day: "numeric" },
                      )}
                    </p>
                  </div>
                </li>
              ))
            ) : (
              <li className="py-8 text-center text-[13px] text-[var(--text-muted)]">
                No payouts yet — publish a review to start earning.
              </li>
            )}
          </ul>
        </section>

          <div className="mt-8 flex flex-wrap items-center gap-4">
            <Button href="/reviews/new">Write a review &amp; earn</Button>
          </div>
        </div>
        <ScrollToHash />
      </main>
      {/* Screen/Dashboard draws QuickActions/Button. */}
      <QuickActions />
      <SiteFooter />
    </div>
  );
}
