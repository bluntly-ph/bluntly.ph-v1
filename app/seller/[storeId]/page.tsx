import { SellerOverview } from "@/components/seller/console/SellerOverview";
import { SupportRequestsCard } from "@/components/seller/console/SupportRequestsCard";
import { getConsoleDashboard, getStoreAppeals, parsePeriod } from "@/lib/seller-console";
import { getStoreSupportRequests } from "@/lib/support";

/** Screen/Seller/Overview (Figma 8190:20643). The layout has already checked ownership. */
export default async function SellerOverviewPage({
  params,
  searchParams,
}: {
  params: Promise<{ storeId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { storeId } = await params;
  const period = parsePeriod((await searchParams).period);
  const [dash, appeals, support] = await Promise.all([
    getConsoleDashboard(storeId, period),
    getStoreAppeals(storeId),
    getStoreSupportRequests(storeId),
  ]);
  if (!dash.ok) {
    return (
      <p role="alert" className="py-10 text-center text-[14px] text-[var(--text-secondary)]">
        {dash.reason === "not_owner"
          ? "Only this store's approved owner can open its console."
          : "The store's figures could not be loaded. Nothing has changed; try again in a moment."}
      </p>
    );
  }
  // eslint-disable-next-line react-hooks/purity -- a server render's clock, read once.
  const now = Date.now();
  return (
    <div className="flex flex-col gap-6">
      <SellerOverview storeId={storeId} dashboard={dash.dashboard} appeals={appeals} period={period} now={now} />
      <SupportRequestsCard storeId={storeId} requests={support.ok ? support.data : null} />
    </div>
  );
}
