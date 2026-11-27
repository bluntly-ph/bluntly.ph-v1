import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { CaretLeft } from "@phosphor-icons/react/dist/ssr";

import { Figure, ReportFrame, ReportTable, ReportUnavailable } from "@/components/reports/ReportFrame";
import {
  csvHref,
  formatRate,
  formatRating,
  periodFromSearch,
} from "@/components/reports/report-model";
import { SiteFooter } from "@/components/site/SiteFooter";
import { SiteHeader } from "@/components/site/SiteHeader";
import { requireOnboardedUser } from "@/lib/dal";
import {
  getSellerRatingSummary,
  sellerRatingPath,
  type RatingBlock,
  type SellerRatingSummary,
} from "@/lib/reports";

export const metadata: Metadata = { title: "Rating summary — bluntly" };

const DATE = new Intl.DateTimeFormat("en-PH", { dateStyle: "medium", timeZone: "Asia/Manila" });

/**
 * Report 3 — the Seller Rating Summary (docs/REPORTING_MODULE.md).
 *
 * For the store's approved owner (and staff); the API refuses anyone else with
 * 403 `not_store_owner`, so another store's owner can never read this one.
 * Reached from the store dashboard, and reusable by the fuller seller
 * dashboard that follows. Every value is the API's: the overall and graded
 * dimensions are MEDIANS (the approved seller aggregate), means are labelled
 * as reference only.
 */
export default async function SellerRatingReportPage({
  params,
  searchParams,
}: {
  params: Promise<{ id: string }>;
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { id } = await params;
  const me = await requireOnboardedUser();
  const period = periodFromSearch(await searchParams);
  const result = await getSellerRatingSummary(id, period);
  if (!result.ok && result.reason === "not_found") notFound();

  return (
    <div className="flex min-h-dvh flex-col bg-[var(--surface-app)]">
      <SiteHeader user={{ username: me.username, avatarUrl: me.avatar_url, role: me.role }} />
      <main className="mx-auto w-full min-w-0 max-w-[72rem] flex-1 px-4 py-6 md:px-8 md:py-8">
        <Link
          href={`/seller/${id}/insights`}
          className="report-no-print inline-flex items-center gap-1 text-[13px] text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
        >
          <CaretLeft size={16} /> Insights
        </Link>
        <div className="mt-4">
          {result.ok ? (
            <Summary report={result.report} period={period} />
          ) : (
            <ReportUnavailable reason={result.reason} detail={result.detail} />
          )}
        </div>
      </main>
      <SiteFooter />
    </div>
  );
}

function Block({ block, title }: { block: RatingBlock; title: string }) {
  const bars = ["5", "4", "3", "2", "1"];
  const total = block.review_count || 1;
  return (
    <section aria-label={title} className="report-section rounded-[var(--radius-md)] bg-[var(--surface-card)] p-4 shadow-[var(--shadow-card)]">
      <h2 className="text-[14px] font-semibold text-[var(--text-primary)]">{title}</h2>
      <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Figure label="Seller reviews" value={String(block.review_count)} testId="review-count" />
        <Figure
          label="Overall (median)"
          value={formatRating(block.overall_median)}
          hint={`Mean ${formatRating(block.overall_mean)} (reference)`}
          testId="overall-median"
        />
        <Figure
          label="Would recommend"
          value={formatRate(block.recommendation_rate)}
          hint="Share of reviewers who said yes"
          testId="recommendation-rate"
        />
        <Figure label="Store responded" value={String(block.responded)} />
      </div>
      <dl className="mt-4 grid gap-2 md:grid-cols-2">
        {block.dimensions.map((d) => (
          <div key={d.key} className="flex items-baseline justify-between gap-3 border-b border-[var(--border-subtle)] py-1.5 text-[13px]">
            <dt className="text-[var(--text-secondary)]">{d.label}</dt>
            <dd className="text-right font-semibold text-[var(--text-primary)] [font-variant-numeric:tabular-nums]" data-testid={`dim-${d.key}`}>
              {d.kind === "yes_no"
                ? `${formatRate(d.rate)} yes`
                : `${formatRating(d.median)} median · ${formatRating(d.mean)} mean`}
            </dd>
          </div>
        ))}
      </dl>
      <div className="mt-4" aria-label="Overall rating distribution">
        {bars.map((star) => {
          const n = block.distribution[star] ?? 0;
          return (
            <div key={star} className="flex items-center gap-2 text-[12px] text-[var(--text-secondary)]">
              <span className="w-8">{star}★</span>
              <span className="h-2 flex-1 overflow-hidden rounded-full bg-[var(--surface-input)]">
                <span
                  className="block h-full rounded-full bg-[var(--accent-star)]"
                  style={{ width: `${(n / total) * 100}%` }}
                />
              </span>
              <span className="w-6 text-right [font-variant-numeric:tabular-nums]">{n}</span>
            </div>
          );
        })}
      </div>
    </section>
  );
}

function Summary({ report, period }: { report: SellerRatingSummary; period: ReturnType<typeof periodFromSearch> }) {
  return (
    <ReportFrame
      meta={report.meta}
      entity={`${report.seller.display_name} (${report.seller.platform})`}
      action={`/sellers/${report.seller.id}/reports`}
      downloads={[{ label: "Export CSV", href: csvHref(sellerRatingPath(report.seller.id), period) }]}
    >
      <Block block={report.period_summary} title="This period" />
      <Block block={report.all_time_summary} title="All time" />
      <ReportTable
        caption="Seller reviews in this period"
        rows={report.rows}
        rowKey={(r) => r.seller_review_id}
        empty="No seller reviews in this period."
        columns={[
          { header: "Date", cell: (r) => DATE.format(new Date(r.created_at)) },
          { header: "Reviewer", cell: (r) => r.reviewer ?? "—" },
          { header: "Title", cell: (r) => <span className="line-clamp-2 max-w-[16rem]">{r.title ?? "—"}</span> },
          { header: "Overall", cell: (r) => formatRating(r.overall_rating), align: "right" },
          { header: "Service", cell: (r) => r.customer_service, align: "right" },
          { header: "Packaging", cell: (r) => r.packaging_quality, align: "right" },
          { header: "Matched listing", cell: (r) => (r.accuracy ? "Yes" : "No") },
          { header: "Complete", cell: (r) => (r.order_completeness ? "Yes" : "No") },
          { header: "Recommends", cell: (r) => (r.would_recommend ? "Yes" : "No") },
          { header: "Responded", cell: (r) => (r.has_store_response ? "Yes" : "No") },
        ]}
      />
    </ReportFrame>
  );
}
