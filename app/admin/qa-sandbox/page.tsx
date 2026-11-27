import type { Metadata } from "next";
import Link from "next/link";

import { QaSandboxConsole } from "@/components/admin/QaSandboxConsole";
import { getPayoutProvider, getQaSandbox } from "@/lib/moderation";

export const metadata: Metadata = { title: "QA Payments — bluntly admin" };

/**
 * QA sandbox test earnings (owner decision, 2026-09-27). Owner-directed
 * admin-shell extension; no dedicated Figma frame exists.
 */
export default async function QaSandboxPage() {
  const [data, provider] = await Promise.all([getQaSandbox(), getPayoutProvider()]);
  return (
    <div className="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto pb-2">
      <div>
        <h2 className="text-[18px] font-bold text-[var(--text-primary)]">QA Payments</h2>
        <p className="mt-1 max-w-[52rem] text-[13px] text-[var(--text-secondary)]">
          Let QA testers test getting paid. Credit a tester&rsquo;s published review with a sandbox test earning; it
          is ready to withdraw at once. The tester requests a withdrawal on their Transfer page, and it is paid from{" "}
          <Link href="/admin/payouts" className="underline hover:text-[var(--accent-primary)]">
            Payouts
          </Link>{" "}
          through PayPal sandbox. Test earnings are not real money: they are labelled for the tester, never counted as
          revenue or toward the Honesty Fund, and one review can take one.
        </p>
      </div>
      <QaSandboxConsole data={data} allowed={provider?.qa_test_earnings_allowed ?? false} />
    </div>
  );
}
