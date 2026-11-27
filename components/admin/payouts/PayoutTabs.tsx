import Link from "next/link";

export type PayoutTab = "to_send" | "sent" | "failed" | "honesty_fund";

/**
 * The Payouts screen's tab row (Figma 8024:12721, 8085:17825, 8085:18136,
 * 8024:13286): To send, Sent, Failed, Honesty Fund, and QA payments (a
 * console of its own). Shared by /admin/payouts and /admin/honesty-fund.
 */
export function PayoutTabs({
  current,
  counts,
}: {
  current: PayoutTab;
  counts?: { to_send_count?: number; sent_count?: number; failed_count?: number } | null;
}) {
  const tabs: { key: PayoutTab | "qa"; label: string; href: string; count?: number | null }[] = [
    { key: "to_send", label: "To send", href: "/admin/payouts", count: counts?.to_send_count ?? null },
    { key: "sent", label: "Sent", href: "/admin/payouts?view=sent", count: counts?.sent_count ?? null },
    { key: "failed", label: "Failed", href: "/admin/payouts?view=failed", count: counts?.failed_count ?? null },
    { key: "honesty_fund", label: "Honesty Fund", href: "/admin/honesty-fund" },
    { key: "qa", label: "QA payments", href: "/admin/qa-sandbox" },
  ];
  return (
    <nav aria-label="Payout views" className="flex flex-wrap gap-[2px] rounded-[10px] bg-[var(--surface-app)] p-[3px]">
      {tabs.map((v) => (
        <Link
          key={v.key}
          href={v.href}
          aria-current={current === v.key ? "page" : undefined}
          className={`flex items-center gap-[6px] rounded-[8px] px-3 py-[5px] leading-none ${
            current === v.key ? "bg-[var(--surface-card)] shadow-[var(--shadow-segment)]" : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
          }`}
        >
          <span className="text-[14px] font-medium">{v.label}</span>
          {v.count != null ? <span className="text-[12px] text-[var(--text-secondary)]">{v.count}</span> : null}
        </Link>
      ))}
    </nav>
  );
}
