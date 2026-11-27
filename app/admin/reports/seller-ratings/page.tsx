import type { Metadata } from "next";
import Link from "next/link";

import { ReportTable } from "@/components/reports/ReportFrame";
import { formatRating } from "@/components/reports/report-model";
import { Unavailable } from "@/components/site/Unavailable";
import { searchSellers } from "@/lib/sellers";

export const metadata: Metadata = { title: "Seller ratings — bluntly admin" };

/**
 * Report 3 for staff: pick a store, open its Rating Summary.
 *
 * The summary itself is one page (`/sellers/[id]/reports`) shared with the
 * store's owner, so staff and owner read exactly the same report. Staff may
 * open any store's; the API gives an owner only their own.
 */
export default async function SellerRatingsIndex({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const q = ((await searchParams).q ?? "").slice(0, 120);
  const stores = await searchSellers(q, 50, { sort: "reviews" });

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="text-[20px] font-bold text-[var(--text-primary)]">Seller Rating Summary</h1>
        <p className="mt-1 text-[13px] text-[var(--text-secondary)]">
          Choose a store to open its rating summary for any period.
        </p>
      </div>
      <form method="get" className="flex gap-2" role="search">
        <input
          name="q"
          defaultValue={q}
          placeholder="Store name"
          aria-label="Store name"
          className="w-full max-w-[22rem] rounded-[var(--radius-sm)] border border-[var(--border-subtle)] bg-[var(--surface-card)] px-3 py-2 text-[14px]"
        />
        <button type="submit" className="rounded-full border border-[var(--border-subtle)] px-4 text-[13px] font-semibold">
          Search
        </button>
      </form>
      {stores === null ? (
        <Unavailable what="stores" />
      ) : (
        <ReportTable
          caption="Stores"
          rows={stores}
          rowKey={(s) => s.id}
          empty="No store matches that name."
          columns={[
            {
              header: "Store",
              cell: (s) => (
                <Link href={`/sellers/${s.id}/reports`} className="font-semibold hover:text-[var(--accent-primary)]">
                  {s.display_name}
                </Link>
              ),
            },
            { header: "Marketplace", cell: (s) => s.platform },
            { header: "Claimed", cell: (s) => (s.claim_status === "claimed" ? "Yes" : "No") },
            { header: "Seller reviews", cell: (s) => s.review_count, align: "right" },
            { header: "Overall", cell: (s) => formatRating(s.overall_average), align: "right" },
          ]}
        />
      )}
    </div>
  );
}
