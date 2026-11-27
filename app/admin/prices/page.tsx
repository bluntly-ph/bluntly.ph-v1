import type { Metadata } from "next";
import Link from "next/link";

import { PriceObservationDecision } from "@/components/admin/PriceObservationDecision";
import {
  isFiltered,
  PRICE_DEFAULT_SORT,
  PRICE_FILTERS,
  PRICE_KEYS,
  PRICE_PAGE_SIZES,
  PRICE_SORTS,
  priceFilterQuery,
  waitingLine,
} from "@/components/admin/prices/prices-model";
import { ListControls } from "@/components/console/ListControls";
import { Pagination } from "@/components/console/Pagination";
import { clampPage, pageSize } from "@/components/console/pagination-model";
import { flatParams, listHref } from "@/components/console/list-query";
import { getPriceObservationPage } from "@/lib/products";

export const metadata: Metadata = { title: "Prices — bluntly admin" };

const PLATFORM: Record<string, string> = {
  shopee: "Shopee",
  lazada: "Lazada",
  amazon: "Amazon",
  other: "Other",
};

/** Why a price waits (price_service.HOLD_*), in the administrator's words. */
const HELD: Record<string, string> = {
  outlier: "Far outside the usual range",
  no_baseline: "No usual range yet",
};

function exactPeso(value: string): string {
  const n = Number(value);
  return Number.isFinite(n)
    ? `₱${n.toLocaleString("en-PH", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`
    : value;
}

function roundPeso(value: string): string {
  const n = Number(value);
  return Number.isFinite(n) ? `₱${Math.round(n).toLocaleString("en-PH")}` : value;
}

/**
 * Community prices waiting for an administrator (FR-2).
 *
 * Every observation starts pending and the public price panel is built from
 * approved ones alone, so nothing a buyer reports reaches a product page
 * without passing here. Exact centavos, not the panel's rounded pesos: a
 * administrator is checking the number itself.
 *
 * Paged with the console Pagination against the API's own count, so every
 * waiting price is reachable and the header states the real backlog (MQA-043).
 * Sort (MQA-007) and filters (MQA-042) live in the URL through ListControls;
 * each price shows what the product usually costs on that marketplace, and a
 * product's name narrows the list to its prices.
 */
export default async function PricesAdminPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = flatParams(await searchParams, PRICE_KEYS);
  const size = pageSize(params.size, PRICE_PAGE_SIZES);
  const requested = Number.parseInt(params.page ?? "1", 10) || 1;
  const filters = priceFilterQuery(params);
  const filtered = isFiltered(params);
  let data = await getPriceObservationPage(filters, requested, size);
  // A stale ?page= past the end (the last price on it was just decided): show
  // the last page that exists rather than an empty table.
  const page = data ? clampPage(requested, data.total, size) : 1;
  if (data && page !== requested) data = await getPriceObservationPage(filters, page, size);
  const rows = data?.items ?? null;
  const productName = params.product ? rows?.find((r) => r.product_id === params.product)?.product_name : null;
  const query = { ...params, page: undefined };

  return (
    <div className="flex min-h-0 flex-1 flex-col gap-3">
      <div className="flex shrink-0 flex-wrap items-start gap-3">
        {/* The shell's h1 names the page ("Price observations"). */}
        <p className="min-w-0 max-w-[52rem] flex-1 text-[13px] text-[var(--text-secondary)]">
          <span data-testid="prices-waiting" className="font-medium text-[var(--text-primary)]">
            {data ? waitingLine(data.total, data.waiting, filtered) : "Unable to load price observations right now."}
          </span>{" "}
          Approve a price that is plausible for the product and marketplace; reject a typo, a
          listing price someone did not pay, or a joke. A product&rsquo;s price range appears once
          three different buyers have an approved price. You cannot decide a price you reported.
        </p>
        <ListControls
          basePath="/admin/prices"
          params={params}
          sorts={PRICE_SORTS}
          defaultSort={PRICE_DEFAULT_SORT}
          filters={PRICE_FILTERS}
          search={{ placeholder: "Product name", label: "Search prices by product" }}
        />
      </div>

      {params.product ? (
        <p className="flex flex-wrap items-center gap-2 text-[13px]">
          <span className="min-w-0 [overflow-wrap:anywhere]">
            Only <span className="font-medium">{productName ?? "one product"}</span>
          </span>
          <Link href={listHref("/admin/prices", params, { product: "", page: "" })} className="text-[var(--accent-primary)] underline underline-offset-4">
            Show every product
          </Link>
        </p>
      ) : null}

      <div className="min-h-0 flex-1 overflow-auto rounded-[var(--radius-md)] bg-[var(--surface-card)] shadow-[var(--shadow-card)]">
        <table className="w-full min-w-[56rem] border-collapse text-left">
          <thead className="sticky top-0 z-10 bg-[var(--surface-app)]">
            <tr className="text-[11px] uppercase tracking-[0.08em] text-[var(--text-muted)]">
              <th className="px-4 py-3 font-medium">Product</th>
              <th className="px-4 py-3 font-medium">Price</th>
              <th className="px-4 py-3 font-medium">Where</th>
              <th className="px-4 py-3 font-medium">Paid on</th>
              <th className="px-4 py-3 font-medium">Reported by</th>
              <th className="px-4 py-3 font-medium">Decision</th>
            </tr>
          </thead>
          <tbody>
            {!rows || rows.length === 0 ? (
              <tr>
                <td colSpan={6} className="px-4 py-12 text-center text-[13px] text-[var(--text-secondary)]">
                  {!rows ? "Unable to load price observations." : filtered ? "No waiting price matches." : "No prices waiting."}
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr key={row.id} className="border-t border-[var(--border-subtle)] align-top text-[13px]">
                  <td className="max-w-[18rem] px-4 py-3 font-medium text-[var(--text-primary)]">
                    <span className="[overflow-wrap:anywhere]">{row.product_name ?? "Unnamed product"}</span>
                    {params.product !== row.product_id ? (
                      <Link
                        href={listHref("/admin/prices", params, { product: row.product_id, page: "" })}
                        className="block text-[12px] font-normal text-[var(--text-secondary)] underline-offset-4 hover:text-[var(--accent-primary)] hover:underline"
                      >
                        Only this product&rsquo;s prices
                      </Link>
                    ) : null}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 [font-variant-numeric:tabular-nums] font-semibold text-[var(--text-primary)]">
                    {exactPeso(row.price)}
                    {HELD[row.hold_reason ?? ""] ? (
                      <span
                        className={`block text-[12px] font-normal ${
                          row.hold_reason === "outlier" ? "text-[var(--accent-danger)]" : "text-[var(--text-muted)]"
                        }`}
                      >
                        {HELD[row.hold_reason ?? ""]}
                      </span>
                    ) : null}
                    {row.usual_median ? (
                      <span className="block text-[12px] font-normal text-[var(--text-secondary)]">
                        Usually {roundPeso(row.usual_median)} · {row.usual_count} approved
                      </span>
                    ) : null}
                  </td>
                  <td className="px-4 py-3 text-[var(--text-secondary)]">
                    {PLATFORM[row.platform] ?? row.platform}
                    {row.variant ? <span className="block text-[12px] [overflow-wrap:anywhere]">{row.variant}</span> : null}
                  </td>
                  <td className="whitespace-nowrap px-4 py-3 text-[12px] text-[var(--text-muted)]">
                    {new Date(row.observed_at).toLocaleDateString("en-PH", { dateStyle: "medium" })}
                  </td>
                  <td className="max-w-[12rem] px-4 py-3 text-[var(--text-secondary)]">
                    <span className="[overflow-wrap:anywhere]">{row.submitter_username ?? "Former member"}</span>
                    <span className="block text-[12px] text-[var(--text-muted)]">
                      {row.source === "review" ? "From a review" : "Price report"}
                    </span>
                  </td>
                  <td className="px-4 py-3">
                    {row.reported_by_viewer ? (
                      <span className="text-[12px] text-[var(--text-secondary)]">You reported this price; another administrator decides it.</span>
                    ) : (
                      <PriceObservationDecision
                        observationId={row.id}
                        label={`${exactPeso(row.price)} for ${row.product_name ?? "this product"}`}
                      />
                    )}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {data && data.total > 0 ? (
        <Pagination
          page={page}
          size={size}
          total={data.total}
          sizes={PRICE_PAGE_SIZES}
          basePath="/admin/prices"
          query={query}
          label="Price pages"
        />
      ) : null}
    </div>
  );
}
