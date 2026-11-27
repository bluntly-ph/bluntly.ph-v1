import type { Metadata } from "next";
import Link from "next/link";
import { Package } from "@phosphor-icons/react/dist/ssr";

import { PayoutTipPage, TipCard } from "@/components/dashboard/PayoutTipPage";
import { pesoSplit } from "@/components/dashboard/contributor-model";
import { requireOnboardedUser } from "@/lib/dal";
import { getPayoutTips } from "@/lib/dashboard";

export const metadata: Metadata = { title: "Add receipts and photos — bluntly" };

function Bar({ label, value, max, tone }: { label: string; value: string | null | undefined; max: number; tone: string }) {
  const n = value == null ? 0 : Number(value);
  return (
    <div className="flex flex-col gap-[6px]">
      <span className="flex items-center justify-between text-[12px] text-[var(--base-gray-400)]">
        {label}
        <span className="text-[14px] font-semibold text-[var(--text-primary)] [font-variant-numeric:tabular-nums]">
          {value == null ? "—" : pesoSplit(value).join("")}
        </span>
      </span>
      <span aria-hidden className="h-2 w-full overflow-hidden rounded-full bg-[var(--surface-app)]">
        <span className="block h-full rounded-full" style={{ width: `${max > 0 ? Math.min(100, (n / max) * 100) : 0}%`, background: tone }} />
      </span>
    </div>
  );
}

/**
 * Payout tip "Add receipts and photos" (Figma 7843:9501): what a published
 * review earns its writer on average with a photo or receipt and without,
 * across all reviewers, then the member's own reviews that have neither.
 *
 * A receipt can only be attached while writing, and a photo only once within
 * 72 hours of publishing (Business Rules §4), so "Add photo" is offered only
 * where that window is still open; the frame's greyed "Add proof" buttons are
 * the closed case, said in words here.
 */
export default async function ProofTipPage() {
  const me = await requireOnboardedUser();
  const tips = await getPayoutTips();
  const max = Math.max(Number(tips?.average_with_proof ?? 0), Number(tips?.average_without_proof ?? 0));
  return (
    <PayoutTipPage
      me={me}
      title="Add receipts and photos"
      lead="Shoppers trust reviews they can see proof for. Here is what reviews earn with it and without."
      action={{ href: "/reviews/new", label: "Write a review with proof" }}
    >
      {!tips ? (
        <p role="alert" className="rounded-[16px] bg-[var(--surface-app)] px-4 py-6 text-[13px] text-[var(--text-secondary)]">
          This could not be loaded right now.
        </p>
      ) : (
        <>
          <TipCard label="Earnings per review, all reviewers" className="flex flex-col gap-3">
            <Bar label="With a photo or receipt" value={tips.average_with_proof} max={max} tone="var(--accent-success)" />
            <Bar label="Without proof" value={tips.average_without_proof} max={max} tone="var(--base-gray-200)" />
          </TipCard>
          <TipCard label="Your reviews missing proof">
            {tips.missing_proof.length === 0 ? (
              <p className="py-2 text-[13px] text-[var(--base-gray-400)]">Every review you&apos;ve published has a photo or receipt.</p>
            ) : (
              <ul className="flex flex-col">
                {tips.missing_proof.map((r) => (
                  <li key={r.review_id} className="flex items-center gap-3 border-b border-[var(--border-subtle)] py-3 last:border-0">
                    {r.product_image_url ? (
                      // eslint-disable-next-line @next/next/no-img-element -- product images come from many hosts
                      <img src={r.product_image_url} alt="" className="size-10 shrink-0 rounded-[10px] object-cover" />
                    ) : (
                      <span aria-hidden className="grid size-10 shrink-0 place-items-center rounded-[10px] bg-[var(--surface-app)] text-[var(--base-gray-400)]">
                        <Package size={20} />
                      </span>
                    )}
                    <span className="flex min-w-0 flex-1 flex-col gap-[2px]">
                      <Link href={`/reviews/${r.review_id}`} className="truncate text-[14px] font-medium text-[var(--text-primary)] hover:underline">
                        {r.product_name}
                      </Link>
                      <span className="text-[12px] text-[var(--base-gray-400)]">
                        Posted {new Date(r.published_at).toLocaleDateString("en-US", { month: "short", day: "numeric", timeZone: "Asia/Manila" })}
                        {r.can_add_photo ? "" : " · photos can only be added in the first 72 hours"}
                      </span>
                    </span>
                    {r.can_add_photo ? (
                      <Link href={`/reviews/${r.review_id}`} className="shrink-0 rounded-full border border-[var(--border-subtle)] px-3 py-[6px] text-[12px] font-medium text-[var(--text-primary)] hover:border-[var(--accent-primary)]">
                        Add photo
                      </Link>
                    ) : null}
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
