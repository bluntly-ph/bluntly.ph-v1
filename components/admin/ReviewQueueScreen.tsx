"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { useState, useTransition } from "react";
import {
  ArrowClockwise,
  ArrowDown,
  ArrowSquareOut,
  CaretDown,
  ChatCircle,
  Flag,
  Package,
  UsersThree,
  WarningCircle,
} from "@phosphor-icons/react/dist/ssr";
import { AllReviewsControls, AllReviewsTab } from "@/components/admin/AllReviewsTab";
import { QaAnswersTab } from "@/components/admin/QaAnswersTab";
import { updatedAtText, type AllReviewsFilters, type AllReviewsResult } from "@/components/admin/all-reviews-model";
import { ReportDecision } from "@/components/admin/ReportDecision";
import { ReportDetailPanel } from "@/components/admin/ReportDetailPanel";
import { SupportQueue } from "@/components/admin/SupportQueue";
import { ReviewsControls, ReviewsTable } from "@/components/admin/queue/QueueReviewsView";
import { PersonCell, TierCell, shortAge } from "@/components/admin/queue/QueueCells";
import { AdminModal } from "@/components/admin/AdminModal";
import { Pagination } from "@/components/console/Pagination";
import { TierBadge, TierReasons } from "@/components/admin/TierBadge";
import type { QaQuestion } from "@/components/admin/qa-answers-model";
import {
  PRIORITY_TIERS,
  TIER_LABELS,
  type PriorityTier,
  type ReportSort,
  type ReportStatus,
  REPORT_PAGE_SIZE,
  REPORT_RESOLUTION_LABELS,
  reportTotalsLine,
  type ReportTotals,
  originLabel,
  REPORT_REASON_LABELS,
  queueHref,
  relativeAge,
  isNewReport,
  reviewIntegrityChecks,
  tabHref,
  isTab,
  type QueueFilters,
  type Tab,
} from "@/components/admin/review-queue-model";
import type { QueueItem, QueueResult, ReportItem } from "@/lib/moderation";
import type { AdminSupportRequest } from "@/lib/support";
import { FIELD_STATES } from "@/components/console/fields";

/**
 * The Review Queue, built to frame 6922:837 "Admin Page - Review Queue"
 * (1280x1943), re-read from Figma on 2026-09-16. It supersedes 5017:3758,
 * which was deleted from the file on 2026-09-09.
 *
 * That frame is its own screen — a table on the left, a stacked detail column
 * on the right, tabs across the top and pagination at the foot.
 *
 * ITS COLUMNS, in its order, are what the table draws: Product, Author, Level,
 * Wilson, Receipt, RIS, Priority, Age. The backend's `review_id` has no column
 * in the frame, so it rides in the row's tooltip instead of adding a ninth.
 *
 * Everything derived rather than served is derived in
 * `review-queue-model.ts`, which the frontend test suite covers directly:
 * Priority from the advisory fraud signals, Wilson from the review's real
 * `wilson_score`, the ID from the backend's own `review_id`.
 *
 * WHERE THE FRAME DRAWS A NUMBER THIS BUILD CANNOT SOURCE, the panel says so
 * in place rather than showing a plausible one. That is not a shortcut around
 * the design: each case below was checked against the backend first, and each
 * is a genuine absence, not unfinished UI.
 *
 *   Views / Shares / Comments / top comment   no admin read path exists
 *   Voting Distribution globe + city bars     write-only geo table, no route
 *   Flagged Voters / High trust / Low trust   no data and no methodology
 *   Voter table (pattern, rate, risk level)   no per-voter risk model exists
 *   Recent Report panel                       reports are on the Report tab
 *   Reverse image search / plagiarism         no provider in this build
 *   Verified Reviews (author card)            not on QueueAuthor
 *
 * A "0" in any of those cells would read as a measurement. On a fraud-review
 * screen that is the one mistake worth designing against.
 *
 * WHAT THE FRAME DOES NOT DRAW AND THE SCREEN HAS ANYWAY is the decision panel
 * (`ReviewDecision`) and the report decisions (`ReportDecision`). The owner
 * ruled on 2026-09-16 that a moderation console which can only inspect is not
 * acceptable, so both are BUSINESS-REQUIRED / DESIGN-SYSTEM ALIGNED: built from
 * this console's own panel and pill vocabulary, not invented styling.
 */

export function ReviewQueueScreen({
  queue,
  filters,
  reports,
  reportTotals = null,
  questions,
  support = null,
  initialTab,
  now,
  allReviews = null,
  allFilters = null,
  openItem = null,
  sellerFlags = null,
  superAdmin = false,
}: {
  /** The API's totals for the Report tab's status (MQA-045): every report, and
   *  the distinct items they are on. Null fields when the API did not answer. */
  reportTotals?: ReportTotals | null;
  /** Open store flags waiting in Sellers › Appeals (MQA-040); null when unknown. */
  sellerFlags?: number | null;
  /** The viewer gives escalated reports their final answer (MQA-005). */
  superAdmin?: boolean;
  /**
   * One policy-ordered page, or the reason there isn't one.
   *
   * Not two arrays any more. The server evaluates every candidate, filters and
   * orders the whole backlog, and only then cuts the page — so a High-priority
   * review submitted after the first fifty arrives on page one instead of
   * sitting unseen behind a client-side sort.
   */
  queue: QueueResult;
  /** The canonical filters, already validated out of the URL by the page. */
  filters: QueueFilters;
  reports: ReportItem[];
  questions: QaQuestion[] | null;
  /** Seller support requests; `null` when the API did not answer. */
  support?: AdminSupportRequest[] | null;
  initialTab: Tab;
  /**
   * The instant the server rendered this page, used for every "3s ago".
   *
   * Not `Date.now()` read inside the component: this is a Client Component, so
   * React renders it on the server too, and a clock read at each render makes
   * the server's HTML and the client's first render disagree on any row posted
   * seconds ago — "Hydration failed … this tree will be regenerated", which
   * `console-health.spec.ts` fails on and which throws away the server's work
   * for the whole table. Passing the timestamp down makes both renders agree.
   */
  now: number;
  /** All Reviews: fetched only when that tab is open, null otherwise. */
  allReviews?: AllReviewsResult | null;
  allFilters?: AllReviewsFilters | null;
  /** A review asked for by `?open=` that is not on the current page. */
  openItem?: QueueItem | null;
}) {
  // The URL is the single source of truth for which tab is showing, so the
  // shell's heading, AdminNav's highlight and this component can never
  // disagree, and the view an administrator is looking at is the view they can
  // paste to someone else. The tabs below are links that change it.
  const searchParams = useSearchParams();
  const urlTab = searchParams?.get("tab") ?? null;
  const tab: Tab = isTab(urlTab) ? urlTab : initialTab;
  const router = useRouter();
  const [refreshing, startRefresh] = useTransition();
  const total = queue.available ? queue.total : 0;

  // The four views the frame draws (Reviews / Answers / Reports / Support).
  // All reviews is not a fifth tab any more: it is the Reviews view with the
  // "Queue" switch off (Switch/Queue, 7943:11507).
  const segments: { key: Tab; label: string; count: number }[] = [
    { key: "reviews", label: "Reviews", count: total },
    { key: "answers", label: "Answers", count: questions?.length ?? 0 },
    // The API's total for the whole status, not this page's rows (MQA-045):
    // the Overview's "Open reports" reads the same count.
    { key: "report", label: "Reports", count: reportTotals?.reports ?? reports.length },
    {
      key: "support",
      label: "Support",
      count: (support ?? []).filter((r) => r.status === "open" || r.status === "in_review").length,
    },
  ];
  const onReviews = tab === "reviews" || tab === "all";

  return (
    <div className="flex min-h-full flex-col">
      {/* Toolbar 7943:11492: the segmented views, then the Queue switch and the
          sort / filter / search controls of the view on screen. */}
      <div className="flex flex-wrap items-center gap-2 pb-4">
        <nav aria-label="Queue views" className="flex flex-wrap gap-[2px] rounded-[10px] bg-[var(--surface-app)] p-[3px]">
          {segments.map((s) => {
            const active = s.key === "reviews" ? onReviews : tab === s.key;
            return (
              <Link
                key={s.key}
                href={tabHref(s.key, filters)}
                scroll={false}
                aria-current={active ? "page" : undefined}
                className={`flex items-center gap-[6px] rounded-[8px] px-3 py-[5px] leading-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)] ${
                  active
                    ? "bg-[var(--surface-card)] text-[var(--text-primary)] shadow-[var(--shadow-segment)]"
                    : "text-[var(--text-secondary)] hover:text-[var(--text-primary)]"
                }`}
              >
                <span className="text-[14px] font-medium">{s.label}</span>
                <span className="text-[12px] text-[var(--text-secondary)]">{s.count}</span>
              </Link>
            );
          })}
        </nav>
        <span className="flex-1" />
        {onReviews ? (
          <Link
            href={tabHref(tab === "all" ? "reviews" : "all", filters)}
            scroll={false}
            role="switch"
            aria-checked={tab === "reviews"}
            title={tab === "reviews" ? "Showing the queue. Switch off to see every review." : "Showing every review. Switch on for the queue."}
            className="flex items-center gap-2 pr-2 text-[14px] font-medium leading-none"
          >
            <span
              aria-hidden
              className={`relative h-[18px] w-[30px] rounded-full transition-colors ${
                tab === "reviews" ? "bg-[var(--base-ink-800)]" : "bg-[var(--base-gray-200)]"
              }`}
            >
              <span
                className={`absolute top-[2px] size-[14px] rounded-full bg-white transition-[left] ${
                  tab === "reviews" ? "left-[14px]" : "left-[2px]"
                }`}
              />
            </span>
            Queue
          </Link>
        ) : null}
        {tab === "reviews" ? <ReviewsControls queue={queue} filters={filters} /> : null}
        {tab === "all" && allFilters ? <AllReviewsControls filters={allFilters} /> : null}
        {/* All reviews draws no Refresh (8060:15564); its menus reload the list. */}
        {tab !== "all" ? (
        <button
          type="button"
          onClick={() => startRefresh(() => router.refresh())}
          disabled={refreshing}
          aria-label="Refresh"
          title={updatedAtText(now)}
          className="grid size-8 place-items-center rounded-[8px] text-[var(--text-secondary)] hover:bg-[var(--surface-app)] disabled:opacity-60"
        >
          <ArrowClockwise size={16} aria-hidden="true" className={refreshing ? "animate-spin" : ""} />
        </button>
        ) : null}
      </div>

      {tab === "reviews" ? (
        <>
          {queue.available && queue.earnGatePhase === "post_seeding" ? (
            <p data-testid="queue-membership" className="pb-3 text-[12px] text-[var(--text-secondary)]">
              Reviews awaiting an earnings decision, and take-downs. A new review joins once its
              trust-weighted votes pass the earnings gate. An administrator&rsquo;s upvote sends a
              review here at once. Switch Queue off to see every review.
            </p>
          ) : null}
          <ReviewsTable queue={queue} filters={filters} reports={reports} now={now} openItem={openItem} />
          <p className="sr-only" data-testid="queue-updated">{updatedAtText(now)}</p>
        </>
      ) : null}

      {tab === "all" && allReviews && allFilters ? (
        <AllReviewsTab result={allReviews} filters={allFilters} now={now} />
      ) : null}

      {tab === "answers" ? <QaAnswersTab questions={questions} now={now} /> : null}

      {tab === "report" ? (
        <ReportsTab
          superAdmin={superAdmin}
          sellerFlags={sellerFlags}
          reports={reports}
          totals={reportTotals}
          now={now}
          filters={filters}
          onChange={(changes) => router.push(queueHref(filters, { ...changes, tab: "report" }))}
        />
      ) : null}

      {tab === "support" ? <SupportQueue requests={support} now={now} /> : null}
    </div>
  );
}

/**
 * Tier filter and queue order (dev note 2026-09-26), shared by the Reviews and
 * Report tabs. Both are links into the URL, so the server filters and orders
 * the whole queue rather than the page on screen.
 */
function TierControls({
  tier,
  sort,
  sortOptions,
  onChange,
  onSort,
}: {
  tier: PriorityTier | "";
  sort: string;
  sortOptions: [string, string][];
  onChange: (changes: Partial<QueueFilters>) => void;
  onSort: (sort: string) => void;
}) {
  const select = `${FIELD_STATES} rounded-[var(--radius-sm)] px-2 py-1 text-[13px]`;
  return (
    <>
      <label className="ml-auto inline-flex items-center gap-1.5 text-[13px] text-[var(--text-secondary)]">
        Tier
        <select
          aria-label="Filter by priority tier"
          value={tier}
          onChange={(e) => onChange({ tier: e.target.value as PriorityTier | "" })}
          className={select}
        >
          <option value="">All tiers</option>
          {PRIORITY_TIERS.map((t) => (
            <option key={t} value={t}>
              {TIER_LABELS[t]}
              {t === "lowest" ? " (routine spot-check)" : ""}
            </option>
          ))}
        </select>
      </label>
      <label className="inline-flex items-center gap-1.5 text-[13px] text-[var(--text-secondary)]">
        Sort
        <select aria-label="Queue order" value={sort} onChange={(e) => onSort(e.target.value)} className={select}>
          {sortOptions.map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </label>
    </>
  );
}

/**
 * Screen/Admin/Queue/Reports 7949:10664: one row per report with what was
 * reported, why, who filed it (a member, or the System's integrity checks),
 * how many reports the item has, its priority tier and its age. Ordered by
 * escalation by default (Business Rules §12: safety and personal-information
 * reports first). A row opens the report, its evidence and the decision.
 */
function ReportsTab({
  reports,
  totals = null,
  now,
  filters,
  onChange,
  sellerFlags = null,
  superAdmin = false,
}: {
  sellerFlags?: number | null;
  superAdmin?: boolean;
  reports: ReportItem[];
  totals?: ReportTotals | null;
  now: number;
  filters: QueueFilters;
  onChange: (changes: Partial<QueueFilters>) => void;
}) {
  // `?report=<id>` (Recent Activity, an escalation notice) opens that report.
  const searchParams = useSearchParams();
  const linked = searchParams.get("report");
  const [picked, setPicked] = useState<string | null>(linked);
  const totalsLine = reportTotalsLine(totals, filters.rstatus ?? "open");
  const current = reports.find((r) => r.report.id === picked) ?? null;

  return (
    <div className="flex flex-col gap-3">
      {sellerFlags ? (
        <p data-testid="seller-flags-callout" className="flex flex-wrap items-center gap-x-2 gap-y-1 rounded-[12px] bg-[var(--status-high-bg)] px-4 py-3 text-[14px]">
          <Flag size={16} weight="fill" className="text-[var(--status-high-fg)]" aria-hidden />
          <span>
            {sellerFlags === 1 ? "1 flag from a store is" : `${sellerFlags} flags from stores are`} waiting. Stores flag reviews of their own store; you decide them in Sellers.
          </span>
          <Link href="/admin/sellers?tab=appeals" className="font-medium underline underline-offset-4">
            Open store flags
          </Link>
        </p>
      ) : null}
      <div className="flex flex-wrap items-center gap-3">
        <label className="relative inline-flex items-center">
          <span className="sr-only">Report status</span>
          <select
            value={filters.rstatus ?? "open"}
            onChange={(e) => onChange({ rstatus: e.target.value as ReportStatus })}
            className="h-8 cursor-pointer appearance-none rounded-full border border-[var(--border-subtle)] bg-[var(--surface-card)] pl-4 pr-8 text-[12px]"
          >
            <option value="open">Open</option>
            <option value="escalated">Escalated</option>
            <option value="resolved">Resolved</option>
            <option value="all">All</option>
          </select>
          <CaretDown size={12} className="pointer-events-none absolute right-3" />
        </label>
        <TierControls
          tier={filters.tier}
          sort={filters.rsort}
          sortOptions={[["escalation", "Escalation order"], ["tier", "Priority tier"], ["newest", "Newest first"], ["oldest", "Oldest first"]]}
          onChange={onChange}
          onSort={(rsort) => onChange({ rsort: rsort as ReportSort })}
        />
      </div>

      <div className="overflow-x-auto rounded-[16px] border border-[var(--border-subtle)]">
        <table className="w-full min-w-[960px] table-fixed border-collapse text-left text-[14px]">
          <caption className="sr-only">Filed reports</caption>
          <colgroup>
            <col style={{ width: "25%" }} />
            <col style={{ width: "24%" }} />
            <col style={{ width: "20%" }} />
            <col style={{ width: "9%" }} />
            <col style={{ width: "13%" }} />
            <col style={{ width: "9%" }} />
          </colgroup>
          <thead className="bg-[var(--surface-app)] text-[12px] text-[var(--text-secondary)]">
            <tr>
              <th scope="col" className="h-10 px-3 font-normal">Reported</th>
              <th scope="col" className="px-3 font-normal">Reason</th>
              <th scope="col" className="px-3 font-normal">From</th>
              <th scope="col" className="px-3 font-normal">Reports</th>
              <th scope="col" className="px-3 font-normal">Priority</th>
              <th scope="col" className="px-3 font-normal">Filed</th>
            </tr>
          </thead>
          <tbody>
            {reports.length === 0 ? (
              <tr>
                <td colSpan={6} className="border-t border-[var(--border-subtle)] px-3 py-10 text-center text-[var(--text-secondary)]">
                  {(filters.rstatus ?? "open") === "open"
                    ? "No open reports. Resolved ones stay in the audit log."
                    : filters.rstatus === "escalated"
                      ? "Nothing is escalated. Escalated reports wait here for a Super Admin."
                      : "No reports match."}
                </td>
              </tr>
            ) : (
              reports.map((r) => {
                const type = r.report.target_type ?? "review";
                const by = r.target?.author_username;
                const what =
                  type === "user" ? "Member account"
                  : type === "comment" ? `Comment${by ? ` by ${by}` : ""}`
                  : type === "answer" ? `Answer${by ? ` by ${by}` : ""}`
                  : type === "question" ? `Question${by ? ` by ${by}` : ""}`
                  : `Review${by ? ` by ${by}` : ""}`;
                const system = r.origin === "system_detected";
                return (
                  <tr
                    key={r.report.id}
                    onClick={() => setPicked(r.report.id)}
                    className="cursor-pointer border-t border-[var(--border-subtle)] hover:bg-[var(--surface-app)]/60"
                  >
                    <td className="px-3 py-[10px]" title={r.target?.title ?? undefined}>
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation();
                          setPicked(r.report.id);
                        }}
                        className="flex w-full items-center gap-[10px] text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--accent-primary)]"
                      >
                        <span className="grid size-8 shrink-0 place-items-center rounded-[8px] bg-[var(--surface-app)] text-[var(--text-muted)]">
                          {type === "user" ? <UsersThree size={16} aria-hidden /> : type === "comment" ? <ChatCircle size={16} aria-hidden /> : <Package size={16} aria-hidden />}
                        </span>
                        <span className="flex min-w-0 flex-col gap-1 leading-4 [&>:first-child]:leading-5">
                          <span className="truncate">
                            {r.target?.product_name ?? r.target?.title ?? (type === "user" ? `@${by ?? "member"}` : "Removed item")}
                          </span>
                          <span className="truncate text-[12px] text-[var(--text-secondary)]">{what}</span>
                        </span>
                      </button>
                    </td>
                    <td className="px-3">
                      <span className="line-clamp-2 font-medium">
                        {r.report.reason ? (REPORT_REASON_LABELS[r.report.reason] ?? r.report.reason) : "Reported"}
                      </span>
                      {r.report.notes ? (
                        <span className="block truncate text-[12px] text-[var(--text-secondary)]" title={r.report.notes}>
                          “{r.report.notes}”
                        </span>
                      ) : null}
                      {(() => {
                        // MQA-003: what the System measured on a reported review, at a glance.
                        const flagged = reviewIntegrityChecks(r.review_signals).filter((c) => c.state === "flagged");
                        return flagged.length ? (
                          <span
                            data-testid="report-row-signals"
                            className="flex items-center gap-1 truncate text-[12px] text-[var(--accent-danger)]"
                            title={flagged.map((c) => `${c.label}: ${c.detail}`).join("\n")}
                          >
                            <WarningCircle size={12} weight="fill" aria-hidden className="shrink-0" />
                            <span className="truncate">{flagged.map((c) => c.label).join(" · ")}</span>
                          </span>
                        ) : null;
                      })()}
                      {r.escalated && !r.report.resolution ? (
                        <span className="text-[12px] text-[var(--accent-danger)]">
                          Top priority{r.urgent_reason ? " · urgent reason" : r.report_surge ? " · report surge" : ""}
                        </span>
                      ) : null}
                    </td>
                    <td className="px-3">
                      {system ? (
                        <span className="flex items-center gap-2">
                          <span className="grid size-7 place-items-center rounded-full bg-[var(--surface-app)] text-[12px] font-semibold text-[var(--accent-primary)]">b</span>
                          System
                        </span>
                      ) : (
                        <PersonCell
                          name={r.reporter?.display_name ?? r.reporter?.username ?? "Former member"}
                          stage={r.reporter?.trust_stage}
                          href={r.reporter ? `/admin/people/${r.reporter.id}` : undefined}
                        />
                      )}
                    </td>
                    <td className="px-3">{r.target_report_count}</td>
                    <td className="px-3">
                      {r.report.resolution ? (
                        <span className="text-[12px] text-[var(--text-secondary)]">
                          {REPORT_RESOLUTION_LABELS[r.report.resolution]?.split(" — ")[0] ?? r.report.resolution}
                        </span>
                      ) : (
                        <TierCell tier={r.triage?.tier} />
                      )}
                    </td>
                    <td className="px-3 text-[var(--text-secondary)]">
                      <span className="flex flex-wrap items-center gap-1.5">
                        {shortAge(r.report.created_at, now)}
                        {/* MQA-001: a report filed in the last day stands out. */}
                        {isNewReport(r.report.created_at, now) && !r.report.resolution ? (
                          <span data-testid="report-new" className="rounded-full bg-[var(--accent-primary)] px-1.5 py-0.5 text-[10px] font-semibold leading-none text-white">
                            New
                          </span>
                        ) : null}
                      </span>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
      {totals?.reports ? (
        <div className="flex flex-col gap-2">
          {totalsLine ? (
            <p data-testid="report-totals" className="text-[12px] text-[var(--text-secondary)]">{totalsLine}</p>
          ) : null}
          <Pagination
            page={filters.rpage ?? 1}
            size={REPORT_PAGE_SIZE}
            total={totals.reports}
            sizes={[]}
            basePath="/admin/review-queue"
            query={{ ...Object.fromEntries(searchParams.entries()), tab: "report", report: null }}
            pageParam="rpage"
            label="Report pages"
          />
        </div>
      ) : reports.length > 0 ? (
        <p className="text-[12px] text-[var(--text-secondary)]">Showing {reports.length}</p>
      ) : null}

      {current ? (
        <AdminModal
          // MQA-002: the item in the title; the reason leads the body below.
          title={current.target?.product_name ?? current.target?.title ?? "Reported item"}
          subtitle={`${originLabel([current.origin ?? "user_reported"])} · filed ${relativeAge(current.report.created_at, now)}`}
          onClose={() => setPicked(null)}
        >
          <div className="grid gap-5 p-6 md:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
            <div className="flex flex-col gap-4">
              {/* MQA-002: the reason first and largest, the reporter's words
                  under it, then the two ways to look further - each its own
                  control - then the tier and the decision. */}
              <section aria-label="Report reason" data-testid="report-reason" className="rounded-[12px] bg-[var(--surface-app)] p-4">
                <p className="text-[11px] font-medium uppercase tracking-[0.06em] text-[var(--text-secondary)]">Reported for</p>
                <p className="mt-1 text-[18px] font-semibold leading-tight">
                  {current.report.reason ? (REPORT_REASON_LABELS[current.report.reason] ?? current.report.reason) : "Reported"}
                </p>
                {current.report.notes ? (
                  <p className="mt-2 text-[14px] leading-[21px] [overflow-wrap:anywhere]">“{current.report.notes}”</p>
                ) : (
                  <p className="mt-2 text-[13px] text-[var(--text-secondary)]">
                    {current.origin === "system_detected" ? "Filed by the System's integrity checks." : "No note from the reporter."}
                  </p>
                )}
              </section>
              <div className="flex flex-wrap gap-2">
                {current.target?.link ? (
                  <Link
                    href={current.target.link}
                    className="inline-flex h-9 items-center gap-1.5 rounded-full border border-[var(--text-primary)] px-4 text-[13px] hover:bg-[var(--surface-app)]"
                  >
                    Open the reported item <ArrowSquareOut size={14} aria-hidden />
                  </Link>
                ) : null}
                <a
                  href="#report-detail"
                  className="inline-flex h-9 items-center gap-1.5 rounded-full px-3 text-[13px] text-[var(--accent-trust)] hover:underline md:hidden"
                >
                  Why was this reported? <ArrowDown size={14} aria-hidden />
                </a>
              </div>
              {current.triage ? (
                <div className="border-t border-[var(--border-subtle)] pt-3 text-[14px]">
                  <TierBadge triage={current.triage} />
                  <TierReasons triage={current.triage} />
                </div>
              ) : null}
              {current.report.resolution === "escalated" ? (
                <>
                  <p data-testid="report-escalated" className="rounded-[12px] bg-[var(--status-high-bg)] px-3 py-2 text-[14px]">
                    Escalated to a Super Admin{current.report.resolved_at ? ` ${relativeAge(current.report.resolved_at, now)}` : ""}.{" "}
                    {superAdmin ? "Give it its final answer below." : "A Super Admin decides it; it stays under Escalated until then."}
                  </p>
                  {superAdmin ? <ReportDecision item={current} /> : null}
                </>
              ) : current.report.resolution ? (
                <p className="text-[14px] text-[var(--text-secondary)]">
                  {REPORT_RESOLUTION_LABELS[current.report.resolution] ?? current.report.resolution}
                </p>
              ) : (
                <ReportDecision item={current} />
              )}
            </div>
            <ReportDetailPanel item={current} now={now} />
          </div>
        </AdminModal>
      ) : null}
    </div>
  );
}

