import { SellerReviews } from "@/components/seller/console/SellerReviews";
import { getConsoleDashboard, getStoreAppeals } from "@/lib/seller-console";
import { getAllSellerReviews } from "@/lib/sellers";
import { getSessionToken } from "@/lib/session";

const MAX = 1000;

/** Screen/Seller/Reviews (Figma 8196:20870). The layout has already checked ownership. */
export default async function SellerReviewsPage({
  params,
  searchParams,
}: {
  params: Promise<{ storeId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { storeId } = await params;
  const asked = (await searchParams).respond;
  const respondTo = typeof asked === "string" && asked ? asked : null;
  const [dash, loaded, appeals] = await Promise.all([
    getConsoleDashboard(storeId),
    getAllSellerReviews(storeId, await getSessionToken(), MAX),
    getStoreAppeals(storeId),
  ]);
  if (!dash.ok || loaded === null) {
    return (
      <p role="alert" className="py-10 text-center text-[14px] text-[var(--text-secondary)]">
        Your reviews could not be loaded. Nothing has changed; try again in a moment.
      </p>
    );
  }
  const { reviews, capped } = loaded;
  const a = dash.dashboard.analytics;
  const open = new Set(["open", "substantiation_requested"]);
  // eslint-disable-next-line react-hooks/purity -- a server render's clock, read once.
  const now = Date.now();
  return (
    <SellerReviews
      storeName={dash.dashboard.seller.display_name}
      reviews={reviews}
      flagged={(appeals ?? []).filter((x) => open.has(x.status)).map((x) => x.seller_review_id)}
      summary={{
        reviewCount: a?.review_count ?? reviews.length,
        responses: a?.responses_total ?? 0,
        responseRate: a?.response_rate ?? null,
        medianReplyHours: a?.median_reply_hours ?? null,
      }}
      capped={capped}
      respondTo={respondTo}
      now={now}
    />
  );
}
