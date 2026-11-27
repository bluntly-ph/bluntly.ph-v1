import type { Metadata } from "next";
import { ArrowRight, Shield, Star } from "@phosphor-icons/react/dist/ssr";

import { Ring } from "@/components/dashboard/ContributorDashboard";
import { PayoutTipPage, TipCard } from "@/components/dashboard/PayoutTipPage";
import { pesoSplit } from "@/components/dashboard/contributor-model";
import { requireOnboardedUser } from "@/lib/dal";
import { getContributorDashboard } from "@/lib/dashboard";

export const metadata: Metadata = { title: "Honest low-star reviews pay too — bluntly" };

function Route({ stars, note, to, colour }: { stars: number; note: string; to: string; colour: string }) {
  return (
    <li className="flex items-center gap-3 rounded-[16px] bg-[var(--surface-app)] px-3 py-3">
      <span className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="flex gap-[2px]" aria-label={`${stars} stars`}>
          {[1, 2, 3, 4, 5].map((i) => (
            <Star key={i} size={14} weight="fill" aria-hidden className={i <= stars ? (stars >= 3 ? "text-[var(--accent-success)]" : "text-[var(--accent-danger)]") : "text-[var(--base-gray-400)]"} />
          ))}
        </span>
        <span className="text-[12px] text-[var(--base-gray-400)]">{note}</span>
      </span>
      <ArrowRight size={14} aria-hidden className="text-[var(--base-gray-400)]" />
      <span className="flex w-[120px] items-center gap-[6px] text-[14px] font-medium">
        <span aria-hidden className="size-2 rounded-full" style={{ background: colour }} />
        {to}
      </span>
    </li>
  );
}

/**
 * Payout tip "Honest low-star reviews pay too" (Figma 7844:9529): reviews of
 * 3★ and up earn commission; 2★ and below are routed to the Honesty Fund
 * (honesty_fund_service), so an honest bad review is never a loss. The
 * member's Honesty Score and what the Fund has paid them close the page.
 */
export default async function HonestTipPage() {
  const me = await requireOnboardedUser();
  const d = await getContributorDashboard("week", "this");
  return (
    <PayoutTipPage
      me={me}
      title="Honest low-star reviews pay too"
      lead="Reviews rated 2★ or lower are paid from the Honesty Fund, so an honest bad review never costs you."
      action={{ href: "/reviews/new", label: "Write a review" }}
    >
      <TipCard label="Where your earnings come from">
        <ul className="flex flex-col gap-2">
          <Route stars={4} note="3★ and up" to="Commission" colour="var(--accent-primary)" />
          <Route stars={2} note="2★ and below" to="Honesty Fund" colour="var(--chart-honesty-fund)" />
        </ul>
      </TipCard>
      {d ? (
        <section aria-label="Honesty Score" className="w-full rounded-[32px] bg-[var(--surface-app)] p-[3px]">
          <div className="flex items-center gap-4 rounded-[32px] bg-[var(--surface-card)] px-5 py-4">
            <Ring size={72} stroke={7} fraction={Math.max(0, Math.min(1, d.honesty_score / 100))} colour="var(--chart-honesty-fund)">
              <span className="text-[16px]">{d.honesty_score}</span>
            </Ring>
            <div className="flex min-w-0 flex-1 flex-col gap-1">
              <span className="flex items-center gap-1 text-[14px] font-semibold leading-none">
                <Shield size={16} weight="fill" aria-hidden className="text-[var(--accent-trust)]" />
                Honesty Score
              </span>
              <p className="text-[12px] leading-[1.5] text-[var(--base-gray-400)]">
                Your share of the Fund grows with it. {pesoSplit(d.honesty_fund_earned).join("")} earned so far.
              </p>
            </div>
          </div>
        </section>
      ) : null}
    </PayoutTipPage>
  );
}
