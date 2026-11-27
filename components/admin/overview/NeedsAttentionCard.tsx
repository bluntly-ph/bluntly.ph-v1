import Link from "next/link";
import {
  CaretRight,
  ChatCircleDots,
  Flag,
  Headset,
  ImageSquare,
  LinkSimple,
  Package,
  Scales,
  ShieldCheck,
  Signpost,
  Tag,
  Wallet,
  WarningCircle,
} from "@phosphor-icons/react/dist/ssr";

import { attentionColumns, attentionOpen } from "@/components/admin/overview/overview-model";
import { Chip } from "@/components/console/Chip";
import type { AttentionGroup } from "@/lib/moderation";

/**
 * "Needs attention" (Card/NeedsAttention 8444:38688, Screen/Admin/Overview v4,
 * read 2026-10-05): Moderation, Integrity and Money in the first column,
 * Catalog and Sellers in the second (attentionColumns), every row a quick link
 * to the list it counts (GET /admin/analytics/needs-attention; the counting
 * rules are in needs_attention_service). The Super Admin's routing row reads
 * "Escalated" with a Super chip, as v4 draws it.
 *
 * Past-due reviews and failed payouts are the two red pills, as drawn: they are
 * the rows where waiting costs someone something. A count the backend could not
 * compute reads "—", never 0.
 */

const ROW: Record<string, { href: string; Icon: typeof Flag; critical?: boolean }> = {
  reviews_past_due: { href: "/admin/review-queue?sla=overdue", Icon: WarningCircle, critical: true },
  answers_to_moderate: { href: "/admin/review-queue?tab=answers", Icon: ChatCircleDots },
  open_reports: { href: "/admin/review-queue?tab=report", Icon: Flag },
  support_requests: { href: "/admin/review-queue?tab=support", Icon: Headset },
  under_investigation: { href: "/admin/reviewers", Icon: ShieldCheck },
  it_depends_routing: { href: "/admin/special-routing", Icon: Signpost },
  products_to_review: { href: "/admin/products", Icon: Package },
  price_submissions: { href: "/admin/prices", Icon: Tag },
  products_without_image: { href: "/admin/products", Icon: ImageSquare },
  seller_claims_appeals: { href: "/admin/sellers", Icon: Scales },
  reviews_needing_link: { href: "/admin/affiliate-links?tab=links", Icon: LinkSimple },
  failed_payouts: { href: "/admin/payouts", Icon: Wallet, critical: true },
};

/** v4's own words for a row, where it renames the API's label. */
const LABEL: Record<string, string> = { it_depends_routing: "Escalated" };
const SUPER_ONLY = new Set(["it_depends_routing"]);

export function NeedsAttentionCard({ groups }: { groups: AttentionGroup[] | null }) {
  const columns = attentionColumns(groups ?? []);
  // One item can sit in two rows (a past-due review that is also reported), so
  // this is a sum of the rows, said as such in the tooltip.
  const open = attentionOpen(groups ?? []);

  return (
    <section
      aria-labelledby="attention-heading"
      className="flex min-w-0 flex-col gap-4 rounded-[16px] border border-[var(--border-subtle)] bg-[var(--surface-card)] p-5"
    >
      <div className="flex items-center gap-1">
        <h2 id="attention-heading" className="inline-flex items-center gap-1 text-[16px] font-semibold leading-none">
          Needs attention
          <CaretRight size={14} className="text-[var(--text-secondary)]" />
        </h2>
        <span className="flex-1" />
        {groups ? (
          <span
            className="text-[12px] leading-none text-[var(--text-secondary)]"
            title="The sum of the rows below; one item can appear in two rows."
          >
            {open} open
          </span>
        ) : null}
      </div>

      {groups === null ? (
        <p role="status" className="text-[13px] text-[var(--text-secondary)]">
          These counts could not be loaded. The lists themselves are still reachable from the rail.
        </p>
      ) : (
        <div className="grid flex-1 gap-x-7 gap-y-5 sm:grid-cols-2">
          {columns.map((column, c) => (
            <div key={c} className="flex flex-col gap-5">
              {column.map((group) => {
                return (
                  <div key={group.key}>
                    <h3 className="pb-[6px] text-[12px] font-medium leading-none text-[var(--text-secondary)]">
                      {group.label}
                    </h3>
                    <ul>
                      {group.items.map((item) => {
                        const meta = ROW[item.key];
                        const Icon = meta?.Icon ?? Flag;
                        const red = meta?.critical && (item.count ?? 0) > 0;
                        return (
                          <li key={item.key} className="border-t border-[var(--border-subtle)]">
                            <Link
                              href={meta?.href ?? "/admin"}
                              className="flex items-center gap-[10px] py-[9px] text-[14px] leading-none hover:text-[var(--accent-primary)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
                            >
                              <Icon size={18} className={`shrink-0 ${red ? "text-[var(--status-critical-fg)]" : ""}`} />
                              <span className="min-w-0 flex-1">
                                {LABEL[item.key] ?? item.label.replaceAll("\"", "")}
                                {SUPER_ONLY.has(item.key) ? (
                                  <Chip tone="muted" className="ml-2 h-5 px-2 align-middle">
                                    Super
                                  </Chip>
                                ) : null}
                                {/* A second, named figure: "Open reports 6 · on 4 items" (MQA-045). */}
                                {item.detail ? (
                                  <span className="ml-1.5 text-[12px] text-[var(--text-secondary)]">{item.detail}</span>
                                ) : null}
                              </span>
                              <span
                                className={
                                  red
                                    ? "rounded-full bg-[var(--status-critical-bg)] px-2 py-px font-semibold text-[var(--status-critical-fg)]"
                                    : "font-semibold"
                                }
                                aria-label={item.count === null ? "count unavailable" : undefined}
                              >
                                {item.count ?? "—"}
                              </span>
                              <CaretRight size={14} className="text-[var(--text-secondary)]" />
                            </Link>
                          </li>
                        );
                      })}
                    </ul>
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
