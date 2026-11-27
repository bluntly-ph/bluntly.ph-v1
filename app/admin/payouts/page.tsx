import type { Metadata } from "next";

import { PayoutsScreen } from "@/components/admin/payouts/PayoutsScreen";
import { flatParams } from "@/components/console/list-query";
import { getAdminPayouts, getPayoutProvider, getPayoutSummary } from "@/lib/moderation";

export const metadata: Metadata = { title: "Payouts — bluntly admin" };

/**
 * Where reviewers' withdrawal requests are paid (Business Rules §15/§19), built
 * to Figma Screen/Admin/Payouts (8024:12721; meeting 2026-10-02).
 *
 * The money path, in order: a marketplace report is imported and each sale
 * credited to its reviewer (still clearing) → the marketplace's own payout for
 * that month is recorded, which clears it → the reviewer requests a withdrawal
 * of cleared money → the owner transfers it and marks it sent here with the
 * transaction ID. The first two steps are on Affiliate; QA testers' test
 * earnings skip them (QA payments tab).
 */
export default async function PayoutsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const sp = await searchParams;
  const raw = Array.isArray(sp.view) ? sp.view[0] : sp.view;
  const view = raw === "sent" || raw === "failed" ? raw : "to_send";
  const [provider, payouts, summary] = await Promise.all([
    getPayoutProvider(),
    getAdminPayouts(view === "sent" ? ["paid"] : view === "failed" ? ["failed"] : ["scheduled", "processing"]),
    getPayoutSummary(),
  ]);
  return (
    <PayoutsScreen
      view={view}
      query={flatParams(sp, ["view", "sort", "amount", "q", "page", "size"])}
      payouts={payouts}
      summary={summary}
      provider={provider}
      // eslint-disable-next-line react-hooks/purity -- read once per request, on the server
      now={Date.now()}
    />
  );
}
