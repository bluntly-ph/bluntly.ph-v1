import { SellerAppeals } from "@/components/seller/console/SellerAppeals";
import { flatParams } from "@/components/console/list-query";
import { getStoreAppeals } from "@/lib/seller-console";

/** Screen/Seller/Appeals (Figma 8196:21910). The layout has already checked ownership. */
export default async function SellerAppealsPage({
  params,
  searchParams,
}: {
  params: Promise<{ storeId: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { storeId } = await params;
  const sp = await searchParams;
  const raw = sp.tab;
  const query = flatParams(sp, ["sort", "status", "rating", "q"]);
  // A notification links straight to a tab (?tab=decided).
  const tab = raw === "decided" || raw === "all" ? raw : "progress";
  const appeals = await getStoreAppeals(storeId);
  if (appeals === null) {
    return (
      <p role="alert" className="py-10 text-center text-[14px] text-[var(--text-secondary)]">
        Your flags could not be loaded. Nothing has changed; try again in a moment.
      </p>
    );
  }
  // eslint-disable-next-line react-hooks/purity -- a server render's clock, read once.
  const now = Date.now();
  // Keyed on the query: a new sort or filter starts on page 1 (the tab is in the URL too).
  return <SellerAppeals key={JSON.stringify(query)} storeId={storeId} appeals={appeals} now={now} initialTab={tab} query={query} />;
}
