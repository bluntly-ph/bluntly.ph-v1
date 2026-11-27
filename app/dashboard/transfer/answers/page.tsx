import type { Metadata } from "next";
import Link from "next/link";
import { CaretRight } from "@phosphor-icons/react/dist/ssr";

import { Money } from "@/components/dashboard/DashboardParts";
import { PayoutTipPage, TipCard } from "@/components/dashboard/PayoutTipPage";
import { requireOnboardedUser } from "@/lib/dal";
import { getPayoutTips } from "@/lib/dashboard";
import { relativeTime } from "@/lib/relative-time";

export const metadata: Metadata = { title: "Answer open questions — bluntly" };

/**
 * Payout tip "Answer open questions" (Figma 7844:9469): how many answers the
 * member wrote this month, what answers have earned them (net of returns),
 * and up to three questions nobody has answered yet in the first category
 * they chose at onboarding (any category when none was chosen).
 */
export default async function AnswerTipPage() {
  const me = await requireOnboardedUser();
  const tips = await getPayoutTips();
  // eslint-disable-next-line react-hooks/purity -- read once per request, on the server
  const now = Date.now();
  return (
    <PayoutTipPage
      me={me}
      title="Answer open questions"
      lead="Helpful answers earn commission when someone buys through them."
      action={{ href: "/questions", label: "Browse open questions" }}
    >
      {!tips ? (
        <p role="alert" className="rounded-[16px] bg-[var(--surface-app)] px-4 py-6 text-[13px] text-[var(--text-secondary)]">
          Your answers could not be loaded right now.
        </p>
      ) : (
        <>
          <section aria-label="Your answers" className="w-full rounded-[32px] bg-[var(--surface-app)] p-[3px]">
            <div className="grid grid-cols-2 gap-3 rounded-[32px] bg-[var(--surface-card)] px-5 py-4">
              <div className="flex flex-col gap-1">
                <span className="text-[12px] text-[var(--base-gray-400)]">Answers this month</span>
                <span className="text-[20px] font-semibold leading-none [font-variant-numeric:tabular-nums]">{tips.answers_this_month}</span>
              </div>
              <div className="flex flex-col gap-1">
                <span className="text-[12px] text-[var(--base-gray-400)]">Earned from answers</span>
                <Money value={tips.earned_from_answers} whole="text-[20px]" cents="text-[14px]" />
              </div>
            </div>
          </section>
          <TipCard label={tips.category_label ? `Waiting in ${tips.category_label}` : "Waiting for an answer"}>
            {tips.open_questions.length === 0 ? (
              <p className="py-2 text-[13px] text-[var(--base-gray-400)]">Every question here has an answer right now.</p>
            ) : (
              <ul className="flex flex-col">
                {tips.open_questions.map((q) => (
                  <li key={q.id} className="border-b border-[var(--border-subtle)] last:border-0">
                    <Link href={`/questions/${q.id}`} className="flex items-center gap-3 py-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]">
                      <span className="flex min-w-0 flex-1 flex-col gap-1">
                        <span className="line-clamp-2 text-[14px] font-medium leading-[1.3] text-[var(--text-primary)]">{q.body}</span>
                        <span className="truncate text-[12px] text-[var(--base-gray-400)]">
                          {[q.product_name, relativeTime(q.created_at, now)].filter(Boolean).join(" · ")}
                        </span>
                      </span>
                      <CaretRight size={16} aria-hidden className="shrink-0 text-[var(--base-gray-400)]" />
                    </Link>
                  </li>
                ))}
              </ul>
            )}
          </TipCard>
        </>
      )}
    </PayoutTipPage>
  );
}
